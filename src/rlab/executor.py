"""Trusted, bounded mutation controller over public BrowserPort evidence.

No model, authority, task-spec or evaluation access. This is source for the
controller, not a browser worker or a demonstrated process isolation boundary.
An adapter must enforce each supplied absolute deadline; synchronous Python
cannot preempt an adapter that ignores it.
"""
from dataclasses import dataclass, replace
from typing import Literal
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from .contracts import FailedAction, HistoryRead, Intent, Origin, Target
from .actions import Action, validate_action
from .ports import (ActionReceipt, BrowserPort, InteractionPort, InteractionReceipt,
                    PreparedCancellationError, UnboundActionResponse)
from .recovery import Reconciliation, resolve
from .views import Page

Arm = Literal["R0", "R1", "R2", "R3", "R23"]
Disposition = Literal["acknowledged", "committed", "returned", "abstained", "cap_abort", "harness_unknown"]


@dataclass(frozen=True)
class Step:
    kind: str
    request_id: str
    origin: Origin
    started_ns: int
    completed_ns: int
    outcome: str


@dataclass(frozen=True)
class ExecutionResult:
    root_intent_id: str
    arm: Arm
    disposition: Disposition
    receipts: tuple[ActionReceipt, ...]
    steps: tuple[Step, ...]
    reason: str = ""
    cancelled_request_ids: tuple[str, ...] = ()
    pending_cleanup_request_ids: tuple[str, ...] = ()
    uncertain_request_ids: tuple[str, ...] = ()
    request_id: str = ""


class CapExceeded(Exception):
    """An operation was refused before dispatch or exceeded a trusted limit."""


class InvalidEvidence(Exception):
    """Adapter identity/timing cannot support a recovery decision."""


class ReconciliationExpired(CapExceeded):
    """Visible evidence stayed inconclusive within the fixed recovery window."""


def allowed_path(path: str, start_path: str) -> bool:
    """Closed task routes only; no URLs, encoding tricks, admin or other runs.

    A future navigation bridge must also check actual origin, redirects, method,
    downloads and uploads. This lexical helper alone is not network isolation.
    """
    if not isinstance(path, str) or not isinstance(start_path, str):
        return False
    if any(c in path for c in ("%", "\\", "\x00", "\r", "\n", "\t")):
        return False
    parsed = urlsplit(path)
    return (path.startswith("/") and not path.startswith("//")
            and not parsed.scheme and not parsed.netloc and not parsed.query
            and not parsed.fragment and unquote(path) == path
            and all(part not in {".", ".."} for part in path.split("/"))
            and path in {start_path, start_path + "/history", start_path + "/action"})


class Executor:
    """One run/epoch, shared caps and one automatic retry per root intent.

    Every observe, history read, wait and mutation consumes one of at most 40
    operation slots, including failures and controller work. Root IDs are
    captured here and cannot be resubmitted to reset the wrapper's retry cap.
    A later actor-issued direct action must get a new root (R0 may recover).
    All retained payload fields originate in the initial visible action.
    """
    def __init__(self, port: BrowserPort, *, max_actions: int = 40,
                 run_budget_ns: int = 180_000_000_000,
                 action_budget_ns: int = 3_000_000_000,
                 reconciliation_budget_ns: int = 4_000_000_000,
                 max_probes: int = 8, poll_wait_ns: int = 500_000_000,
                 absolute_deadline_ns: int | None = None):
        values = (max_actions, port.public.max_actions, run_budget_ns,
                  action_budget_ns, reconciliation_budget_ns, max_probes, poll_wait_ns)
        if any(type(v) is not int or v <= 0 for v in values):
            raise ValueError("positive integer limits required")
        if not port.clock_id or not allowed_path(port.public.start_path, port.public.start_path):
            raise ValueError("trusted clock and exact local start route required")
        self.port = port
        self.public = port.public
        self.clock_id = port.clock_id
        self.started_ns = port.now_ns()
        if absolute_deadline_ns is not None and (
                type(absolute_deadline_ns) is not int or absolute_deadline_ns < 0):
            raise ValueError("absolute run deadline must be a nonnegative integer")
        self.deadline_ns = self.started_ns + min(run_budget_ns, 180_000_000_000)
        if absolute_deadline_ns is not None:
            self.deadline_ns = min(self.deadline_ns, absolute_deadline_ns)
        self.max_actions = min(max_actions, port.public.max_actions, 40)
        self.action_budget_ns = min(action_budget_ns, 3_000_000_000)
        self.reconciliation_budget_ns = reconciliation_budget_ns
        self.max_probes = max_probes
        self.poll_wait_ns = poll_wait_ns
        self.steps: list[Step] = []
        self._last_ns = self.started_ns
        self._captured: dict[str, Intent] = {}
        self._used: set[str] = set()
        self._prepared_request: str | None = None
        self._cleanup_error: str | None = None
        self._action_error: str | None = None
        self._unbound_request_id: str | None = None
        self._correlation_ids: set[str] = set()
        self._dispatched_ids: set[str] = set()
        self.operation_count = 0
        self.history_reads: list[HistoryRead] = []

    def _claim_correlation(self, supplied: str | None = None) -> str:
        value = uuid4().hex if supplied is None else supplied
        if (not isinstance(value, str) or not 1 <= len(value) <= 128
                or any(not (c.isascii() and (c.isalnum() or c in "_-")) for c in value)
                or value in self._correlation_ids):
            raise ValueError("malformed or reused request correlation")
        self._correlation_ids.add(value)
        return value

    def _caller_deadline(self, deadline_ns: int | None) -> int:
        if deadline_ns is not None and (type(deadline_ns) is not int or deadline_ns < 0):
            raise ValueError("absolute integer caller deadline required")
        return min(self.deadline_ns, deadline_ns if deadline_ns is not None else self.deadline_ns)

    def _now(self) -> int:
        now = self.port.now_ns()
        if (self.port.clock_id != self.clock_id or self.port.public != self.public
                or type(now) is not int or now < self._last_ns):
            raise InvalidEvidence("run identity or monotonic clock changed")
        self._last_ns = now
        return now

    def _remember_cleanup_failure(self, failure: PreparedCancellationError) -> None:
        """Latch before fallible clock/trace accounting can mask the exception."""
        self._prepared_request = failure.request_id
        self._cleanup_error = "prepared cancellation failed: trusted reconciliation required"

    def _remember_unbound_response(self, request_id: str) -> None:
        self._unbound_request_id = request_id
        self._action_error = "authoritative action completion unavailable; trusted reconciliation required"
        if self._prepared_request == request_id:
            self._prepared_request = None

    def _begin(self, end_ns: int | None = None) -> tuple[int, int]:
        if self._cleanup_error is not None or self._action_error is not None:
            raise InvalidEvidence(self._cleanup_error or self._action_error)
        now = self._now()
        deadline = min(self.deadline_ns, now + self.action_budget_ns,
                       end_ns if end_ns is not None else self.deadline_ns)
        if self.operation_count >= self.max_actions or now >= self.deadline_ns:
            raise CapExceeded("operation or absolute deadline exhausted")
        if now >= deadline:
            raise ReconciliationExpired("reconciliation window exhausted")
        return now, deadline

    def _read(self, kind: str, end_ns: int | None = None) -> Page | HistoryRead:
        started, deadline = self._begin(end_ns)
        request_id = self._claim_correlation()
        outcome = "unknown"
        timed_out = False
        try:
            try:
                self.operation_count += 1
                value = (self.port.observe(deadline) if kind == "observe"
                         else self.port.history(request_id, deadline))
            except TimeoutError:
                if kind != "history":
                    raise
                timed_out = True
                # An unsuccessful public read is ambiguous, never empty history.
                value = HistoryRead(self.public.run_id, self.public.epoch,
                                    self.clock_id, request_id, started, self._now(),
                                    None, None, (), successful=False, complete=False)
            if kind == "history" and isinstance(value, HistoryRead):
                self.history_reads.append(value)
            completed = self._now()
            if completed >= deadline:
                if end_ns is not None and deadline == end_ns < self.deadline_ns:
                    raise ReconciliationExpired("history exceeded reconciliation window")
                raise CapExceeded("read exceeded deadline")
            if kind == "observe":
                if not isinstance(value, Page) or not value.snapshot_epoch:
                    raise InvalidEvidence("invalid public snapshot")
            elif (not isinstance(value, HistoryRead) or value.request_id != request_id
                  or value.started_ns < started or value.completed_ns > completed):
                raise InvalidEvidence("history not bound to issued read")
            outcome = "timeout" if timed_out else "received"
            return value
        finally:
            self.steps.append(Step(kind, request_id, "controller_resolve", started,
                                   self._now(), outcome))

    def observe(self, *, deadline_ns: int | None = None) -> Page:
        """Actor snapshot acquisition shares the run's operation/time budget."""
        page = self._read("observe", self._caller_deadline(deadline_ns))
        assert isinstance(page, Page)
        return page

    def history(self, *, deadline_ns: int | None = None) -> HistoryRead:
        """Native actor history access; no implicit reconciliation or retry."""
        read = self._read("history", self._caller_deadline(deadline_ns))
        assert isinstance(read, HistoryRead)
        return read

    def perform(self, action: Action, *, request_id: str | None = None,
                deadline_ns: int | None = None) -> InteractionReceipt:
        """Closed non-mutation interaction sharing the existing run/step caps.

        Mutation clicks must go through capture/execute and the selected arm.
        Transport exceptions remain exceptions, never fabricated authority events.
        """
        validate_action(action)
        if action.kind == "click" or action.intent is not None:
            raise ValueError("mutation requires captured intent and recovery arm")
        if not isinstance(self.port, InteractionPort):
            raise ValueError("closed interaction bridge unavailable")
        correlation = self._claim_correlation(request_id)
        started, deadline = self._begin(self._caller_deadline(deadline_ns))
        if action.kind == "wait" and started + action.duration_ms * 1_000_000 >= deadline:
            raise CapExceeded("wait exceeds method/run allowance")
        request_id, outcome = correlation, "unknown"
        try:
            self.operation_count += 1
            receipt = self.port.interact(action, request_id, deadline)
            completed = self._now()
            if (not isinstance(receipt, InteractionReceipt)
                    or (receipt.request_id, receipt.run_id, receipt.epoch, receipt.clock_id) != (
                        request_id, self.public.run_id, self.public.epoch, self.clock_id)
                    or not started <= receipt.response_ns <= completed
                    or receipt.status not in {"acknowledged", "unknown"}):
                raise InvalidEvidence("unbound browser interaction receipt")
            if completed >= deadline:
                raise CapExceeded("browser interaction deadline exceeded")
            if action.kind == "wait" and completed < started + action.duration_ms * 1_000_000:
                raise InvalidEvidence("browser wait was not performed")
            outcome = receipt.status
            return receipt
        finally:
            self.steps.append(Step(action.kind, request_id, "agent_direct", started,
                                   self._now(), outcome))

    def capture(self, operation: str, target_id: str,
                payload: tuple[tuple[str, str], ...], target: Target,
                before_version: int) -> Intent:
        """Capture public intent; never infer a target from private answers."""
        if operation not in {"order", "ticket", "delete"}:
            raise ValueError("unsupported development operation")
        if (not isinstance(target_id, str) or not target_id
                or type(before_version) is not int or before_version < 0
                or not isinstance(target, Target) or not target.ref or not target.snapshot_epoch
                or not isinstance(payload, tuple)
                or any(not isinstance(p, tuple) or len(p) != 2
                       or any(not isinstance(v, str) for v in p) for p in payload)
                or len(dict(payload)) != len(payload) or tuple(sorted(payload)) != payload):
            raise ValueError("invalid captured public intent")
        intent = Intent(uuid4().hex, operation, target_id, payload, target, before_version)
        self._captured[intent.root_intent_id] = intent
        return intent

    def _wait(self, duration_ns: int, end_ns: int | None = None) -> None:
        started, deadline = self._begin(end_ns)
        if started + duration_ns >= deadline:
            if end_ns is not None and deadline == end_ns < self.deadline_ns:
                raise ReconciliationExpired("no further poll fits reconciliation window")
            raise CapExceeded("wait would exhaust absolute deadline")
        outcome = "unknown"
        try:
            self.operation_count += 1
            self.port.wait(duration_ns, deadline)
            completed = self._now()
            if completed < started + duration_ns:
                raise InvalidEvidence("adapter did not perform requested wait")
            if completed >= deadline:
                raise CapExceeded("wait exceeded deadline")
            outcome = "completed"
        finally:
            self.steps.append(Step("wait", uuid4().hex, "controller_resolve",
                                   started, self._now(), outcome))

    def _issue(self, intent: Intent, origin: Origin,
               end_ns: int | None = None, request_id: str | None = None) -> ActionReceipt:
        started, deadline = self._begin(end_ns)
        request_id = self._claim_correlation() if request_id is None else request_id
        if request_id in self._dispatched_ids:
            raise InvalidEvidence("request already dispatched")
        self._correlation_ids.add(request_id)
        self._dispatched_ids.add(request_id)
        outcome = "unknown"
        try:
            try:
                self.operation_count += 1
                receipt = self.port.execute(intent, request_id, origin, deadline)
            except PreparedCancellationError as exc:
                # Do not erase pending state or reinterpret failed cleanup as a
                # lost mutation confirmation eligible for history/retry.
                self._remember_cleanup_failure(exc)
                raise
            except UnboundActionResponse:
                # The request may still be in flight. Latch before fallible
                # accounting and never cancel a possibly issued mutation here.
                self._remember_unbound_response(request_id)
                raise
            except Exception as exc:
                if self._prepared_request == request_id:
                    self._prepared_request = None
                # Dispatch may already have changed server state; no no-effect inference.
                receipt = ActionReceipt(request_id, self.public.run_id, self.public.epoch,
                                        self.clock_id, self._now(), "unknown", type(exc).__name__)
            else:
                if self._prepared_request == request_id:
                    self._prepared_request = None
            try:
                completed = self._now()
                valid = (isinstance(receipt, ActionReceipt)
                         and (receipt.request_id, receipt.run_id, receipt.epoch, receipt.clock_id) == (
                             request_id, self.public.run_id, self.public.epoch, self.clock_id)
                         and type(receipt.response_ns) is int
                         and started <= receipt.response_ns <= completed
                         and type(receipt.status) is str
                         and receipt.status in {"acknowledged", "failed", "unchanged", "unknown"})
            except Exception:
                valid = False
            if not valid:
                self._remember_unbound_response(request_id)
                raise UnboundActionResponse(request_id)
            if completed >= deadline:
                receipt = replace(receipt, response_ns=completed, status="unknown",
                                  error="mutation deadline exceeded; effect unknown")
            outcome = receipt.status
            return receipt
        finally:
            try:
                final_ns = self._now()
            except Exception:
                if self._cleanup_error is None:
                    self._remember_unbound_response(request_id)
                raise
            self.steps.append(Step("mutation", request_id, origin, started, final_ns, outcome))

    def _guard(self, original: Intent, request_id: str,
               end_ns: int | None = None) -> Intent | None:
        # Expose a scheduled DOM boundary BEFORE fresh semantic resolution.
        # The task reuses this ID at mutation, never preparing/firing twice.
        started, deadline = self._begin(end_ns)
        outcome = "unknown"
        try:
            self.operation_count += 1
            self.port.prepare_action(request_id, deadline)
            self._prepared_request = request_id
            if self._now() >= deadline:
                raise CapExceeded("preparation exceeded deadline")
            outcome = "prepared"
        except PreparedCancellationError as exc:
            self._remember_cleanup_failure(exc)
            raise
        finally:
            self.steps.append(Step("prepare", request_id, "controller_resolve",
                                   started, self._now(), outcome))
        page = self._read("observe", end_ns)
        assert isinstance(page, Page)
        target = resolve(original, page.targets, page.snapshot_epoch)
        # Only ref/snapshot change; intended operation, target and fields stay captured.
        return replace(original, target=target) if target is not None else None

    def execute(self, intent: Intent, arm: Arm, *, request_id: str | None = None,
                deadline_ns: int | None = None) -> ExecutionResult:
        if arm not in {"R0", "R1", "R2", "R3", "R23"}:
            raise ValueError("unknown recovery arm")
        if self._cleanup_error is not None or self._action_error is not None:
            pending = (self._prepared_request,) if self._prepared_request is not None else ()
            uncertain = (self._unbound_request_id,) if self._unbound_request_id is not None else ()
            return ExecutionResult(intent.root_intent_id, arm, "harness_unknown", (), (),
                                   self._cleanup_error or self._action_error, (), pending, uncertain,
                                   request_id or "")
        if self._captured.get(intent.root_intent_id) != intent or intent.root_intent_id in self._used:
            raise ValueError("use an unconsumed executor-captured intent")
        self._used.add(intent.root_intent_id)
        correlation = self._claim_correlation(request_id)
        call_end = self._caller_deadline(deadline_ns)
        first_step = len(self.steps)
        receipts: list[ActionReceipt] = []
        recovery_end: int | None = None

        def result(state: Disposition, reason: str = "") -> ExecutionResult:
            cancelled: tuple[str, ...] = ()
            if (self._prepared_request is not None and self._cleanup_error is None
                    and self._action_error is None):
                pending = self._prepared_request
                try:
                    # Trusted non-effect cleanup is not a browser operation;
                    # release pending state even after cap/expiry/refusal.
                    self.port.cancel_action(pending)
                    cancelled = (pending,)
                except Exception as exc:
                    self._cleanup_error = "prepared cancellation failed: " + type(exc).__name__
                else:
                    self._prepared_request = None
            if self._cleanup_error is not None:
                state, reason = "harness_unknown", self._cleanup_error
            elif self._action_error is not None:
                state, reason = "harness_unknown", self._action_error
            pending_cleanup = ((self._prepared_request,)
                               if self._prepared_request is not None else ())
            uncertain = ((self._unbound_request_id,)
                         if self._unbound_request_id is not None else ())
            return ExecutionResult(intent.root_intent_id, arm, state, tuple(receipts),
                                   tuple(self.steps[first_step:]), reason, cancelled, pending_cleanup, uncertain,
                                   correlation)

        try:
            guarded = arm in {"R3", "R23"}
            request_id = correlation
            issued = self._guard(intent, request_id, call_end) if guarded else intent
            if issued is None:
                return result("abstained", "RERESOLVE_REFUSED")
            receipt = self._issue(issued, "controller_resolve" if guarded else "agent_direct",
                                  end_ns=call_end, request_id=request_id)
            receipts.append(receipt)
            if receipt.status == "acknowledged":
                return result("acknowledged")
            if arm in {"R0", "R3"}:
                return result("returned", receipt.error)
            if arm == "R1":
                self._wait(250_000_000, call_end)
                # Exact same submitted ref and immutable fields; deliberately no R3.
                retried = self._issue(issued, "controller_retry", call_end)
                receipts.append(retried)
                return result("acknowledged" if retried.status == "acknowledged" else "returned",
                              retried.error)
            failed = FailedAction(receipt.run_id, receipt.epoch, receipt.clock_id, receipt.response_ns)
            reconciliation = Reconciliation(intent, failed, self.reconciliation_budget_ns,
                                            self.max_probes)
            recovery_end = min(call_end, failed.response_ns + self.reconciliation_budget_ns)
            while True:
                read = self._read("history", recovery_end)
                assert isinstance(read, HistoryRead)
                decision = reconciliation.inspect(read, self._now())
                if decision == "committed":
                    return result("committed")
                if decision == "abstain":
                    return result("abstained", "AMBIGUOUS_ABSTENTION")
                if decision == "retry_once":
                    retry_id = uuid4().hex
                    retry = self._guard(intent, retry_id, recovery_end) if guarded else intent
                    if retry is None:
                        return result("abstained", "RERESOLVE_REFUSED")
                    retried = self._issue(retry, "controller_retry", recovery_end, retry_id)
                    receipts.append(retried)
                    if retried.status == "acknowledged":
                        return result("acknowledged")
                    reconciliation.retry_failed(FailedAction(
                        retried.run_id, retried.epoch, retried.clock_id, retried.response_ns))
                else:
                    self._wait(self.poll_wait_ns, recovery_end)
        except PreparedCancellationError as exc:
            self._remember_cleanup_failure(exc)
            return result("harness_unknown", self._cleanup_error)
        except UnboundActionResponse:
            return result("harness_unknown", self._action_error or "authority response unbound")
        except (CapExceeded, TimeoutError) as exc:
            if self._cleanup_error is not None or self._action_error is not None:
                # Failed cleanup wins even if final clock accounting raised a
                # timeout. Do not query that failed clock again or retry cleanup.
                return result("harness_unknown", self._cleanup_error or self._action_error)
            # Adapter wait/observe methods can raise at their post-call check.
            # Preserve the recovery disposition even when that lower layer did
            # not raise our specialized exception (e.g. OS sleep overshoot).
            try:
                now = self._now()
            except Exception as invalid:
                return result("harness_unknown", "trusted clock unavailable: " + type(invalid).__name__)
            # Genuine run/method overruns take precedence even if an adapter
            # overshoots a shorter recovery deadline by a large amount.
            if now >= call_end or (
                    self.steps and self.steps[-1].completed_ns >=
                    self.steps[-1].started_ns + self.action_budget_ns):
                return result("cap_abort", str(exc))
            if isinstance(exc, ReconciliationExpired) and recovery_end is not None and recovery_end < call_end:
                return result("abstained", "AMBIGUOUS_ABSTENTION: " + str(exc))
            if (recovery_end is not None and recovery_end < call_end
                    and recovery_end <= now < call_end
                    and self.operation_count < self.max_actions):
                return result("abstained", "AMBIGUOUS_ABSTENTION: " + str(exc))
            return result("cap_abort", str(exc))
        except InvalidEvidence as exc:
            return result("harness_unknown", str(exc))
        except Exception as exc:
            # Unexpected adapter faults never imply absence or restart recovery.
            return result("harness_unknown", type(exc).__name__)
