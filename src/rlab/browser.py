"""Browser adapter SOURCE, requiring an explicit trusted server/browser bridge.

No Playwright import, startup, network, private spec or local-authority handle.
There is deliberately no default bridge: missing clock/lineage/render binding
fails closed. The interface is not evidence of egress isolation or DOM installs.
"""
from dataclasses import asdict, dataclass
from typing import Protocol

from .actions import Action, validate_action
from .contracts import HistoryRead, Intent, Origin, PublicTask
from .executor import Arm, ExecutionResult, Executor
from .ports import (ActionReceipt, InteractionReceipt, PreparedCancellationError,
                    UnboundActionResponse)
from .routing import RoutePolicy
from .snapshot import Snapshot, referenced_target, validate_snapshot
from .views import Page


class BridgeUnavailable(RuntimeError):
    """Actual trusted browser/server integration is not bound."""


@dataclass(frozen=True)
class MediaStatus:
    trace: str = "not_requested"
    video: str = "not_requested"
    error: str = "media not qualified"


@dataclass(frozen=True)
class ContextReceipt:
    run_id: str
    epoch: str
    clock_id: str
    context_id: str
    fresh: bool
    media: MediaStatus
    profile: str = "browser"


class TrustedBridge(Protocol):
    """Operator-installed hook, not selectable by actor input or report files.

    Implementations create a new browser context, install RoutePolicy before
    any navigation, deny redirects/downloads/uploads/admin/other origins on all
    resources, disable arbitrary actor JS and bind POST to trusted intent out of
    band. Server authority-clock responses/history and render acknowledgement
    must arrive on the trusted channel. Browser timeouts cannot manufacture
    them. All method deadlines require real preemption in the future transport.
    No implementation of this privileged boundary is supplied by this module.
    """
    public: PublicTask
    clock_id: str

    def now_ns(self) -> int: ...
    def open_context(self, policy: RoutePolicy, deadline_ns: int) -> ContextReceipt: ...
    def snapshot(self, deadline_ns: int) -> Snapshot: ...
    def prepare_action(self, request_id: str, deadline_ns: int) -> None: ...
    def cancel_action(self, request_id: str) -> None: ...
    def execute(self, intent: Intent, request_id: str, origin: Origin,
                deadline_ns: int) -> ActionReceipt: ...
    def history(self, request_id: str, deadline_ns: int) -> HistoryRead: ...
    def wait(self, duration_ns: int, deadline_ns: int) -> None: ...
    def interact(self, action: Action, request_id: str,
                 deadline_ns: int) -> InteractionReceipt: ...
    def close_context(self) -> None: ...


class BrowserAdapter:
    """Trusted adapter; never expose this object or backend to an actor worker."""
    def __init__(self, bridge: TrustedBridge | None, origin: str, *, allow_convenience: bool = False):
        if bridge is None:
            raise BridgeUnavailable("trusted browser/server bridge is not implemented or bound")
        self.bridge = bridge
        self.public, self.clock_id = bridge.public, bridge.clock_id
        if not self.clock_id:
            raise BridgeUnavailable("authority clock identity missing")
        self.policy = RoutePolicy(origin, self.public.start_path)
        self.context: ContextReceipt | None = None
        self.last_snapshot: Snapshot | None = None
        self.allow_convenience = allow_convenience

    def now_ns(self) -> int:
        if (self.bridge.public != self.public or self.bridge.clock_id != self.clock_id):
            raise BridgeUnavailable("trusted run/clock changed")
        return self.bridge.now_ns()

    def _check(self, deadline_ns: int, *, context: bool = True) -> None:
        if self.now_ns() >= deadline_ns:
            raise TimeoutError("browser adapter deadline")
        if context and self.context is None:
            raise BridgeUnavailable("fresh context not admitted; start the session first")

    def observe(self, deadline_ns: int) -> Page:
        self._check(deadline_ns)
        snapshot = validate_snapshot(self.bridge.snapshot(deadline_ns),
                                     self.public.run_id, self.public.epoch)
        self.policy.authorize(snapshot.url, "GET")
        self._check(deadline_ns)
        self.last_snapshot = snapshot
        return Page(snapshot.snapshot_epoch, snapshot.body, snapshot.targets)

    def prepare_action(self, request_id: str, deadline_ns: int) -> None:
        self._check(deadline_ns)
        # Bridge owns post-hook deadline cleanup and must propagate typed failure.
        self.bridge.prepare_action(request_id, deadline_ns)

    def cancel_action(self, request_id: str) -> None:
        try:
            self.bridge.cancel_action(request_id)
        except Exception as exc:
            if isinstance(exc, PreparedCancellationError):
                raise
            raise PreparedCancellationError(request_id) from exc

    def execute(self, intent: Intent, request_id: str, origin: Origin,
                deadline_ns: int) -> ActionReceipt:
        # The trusted bridge must consume/cancel preparation even if its own
        # pre-dispatch deadline check rejects. Never synthesize server receipts.
        try:
            self.policy.authorize(self.public.start_path + "/action", "POST")
            receipt = self.bridge.execute(intent, request_id, origin, deadline_ns)
            if (not isinstance(receipt, ActionReceipt)
                    or (receipt.request_id, receipt.run_id, receipt.epoch, receipt.clock_id) != (
                        request_id, self.public.run_id, self.public.epoch, self.clock_id)
                    or type(receipt.response_ns) is not int or receipt.response_ns < 0
                    or type(receipt.status) is not str
                    or receipt.status not in {"acknowledged", "failed", "unchanged", "unknown"}):
                raise UnboundActionResponse(request_id)
            return receipt
        except PreparedCancellationError:
            raise
        except UnboundActionResponse:
            raise
        except Exception as exc:
            # A browser/pipe timeout does not prove the server's POST finished.
            # No synthetic response time, history reconciliation or retry is safe.
            raise UnboundActionResponse(request_id) from exc

    def history(self, request_id: str, deadline_ns: int) -> HistoryRead:
        self._check(deadline_ns)
        self.policy.authorize(self.public.start_path + "/history", "GET")
        value = self.bridge.history(request_id, deadline_ns)
        self._check(deadline_ns)
        return value

    def wait(self, duration_ns: int, deadline_ns: int) -> None:
        self._check(deadline_ns)
        self.bridge.wait(duration_ns, deadline_ns)
        self._check(deadline_ns)

    def interact(self, action: Action, request_id: str,
                 deadline_ns: int) -> InteractionReceipt:
        validate_action(action)
        self._check(deadline_ns, context=False)
        if self.context is None:
            if action.kind != "goto" or action.path != self.public.start_path:
                raise BridgeUnavailable("first interaction must open the task start path")
            receipt = self.bridge.open_context(self.policy, deadline_ns)
            if (not isinstance(receipt, ContextReceipt) or receipt.fresh is not True
                    or not isinstance(receipt.context_id, str) or not 1 <= len(receipt.context_id) <= 160
                    or (receipt.run_id, receipt.epoch, receipt.clock_id) != (
                        self.public.run_id, self.public.epoch, self.clock_id)
                    or not isinstance(receipt.media, MediaStatus)):
                raise BridgeUnavailable("fresh context identity not confirmed")
            if receipt.profile != "browser" and not (
                    self.allow_convenience and receipt.profile == "in_process_convenience"):
                raise BridgeUnavailable("convenience profile requires explicit operator opt-in")
            self.context = receipt
        if action.kind == "goto":
            self.policy.authorize(action.path, "GET")
        elif action.kind == "click":
            raise ValueError("click requires captured mutation execution")
        value = self.bridge.interact(action, request_id, deadline_ns)
        self.policy.authorize(value.url, "GET")
        self._check(deadline_ns)
        if action.kind in {"goto", "back", "reload"} and value.status == "acknowledged":
            self.last_snapshot = None
        return value


class BrowserSession:
    """Public action facade; a future worker must receive only a bounded IPC view.

    This in-process facade is not an OS isolation boundary. All operator bridge
    wiring and media stay outside actor snapshots. finish is actor termination,
    never a statement that server effects met an independent oracle.
    """
    def __init__(self, bridge: TrustedBridge | None, origin: str, *,
                 allow_convenience: bool = False, **limits: int):
        self._adapter = BrowserAdapter(bridge, origin, allow_convenience=allow_convenience)
        self._executor = Executor(self._adapter, **limits)
        self.public = self._adapter.public
        self._finished = False

    @property
    def clock_id(self) -> str:
        return self._adapter.clock_id

    def now_ns(self) -> int:
        return self._adapter.now_ns()

    @property
    def context_receipt(self) -> ContextReceipt | None:
        """Trusted operator lifecycle metadata; never an isolation attestation."""
        return self._adapter.context

    def execution_receipt(self) -> dict[str, object]:
        """Actual invoked operations/read receipts, including failed calls.

        The count does not depend on a final clock read succeeding. This operator
        accessor exposes no authority object, private spec or fault schedule.
        """
        return {"actions": self._executor.operation_count,
                "reads": [asdict(read) for read in self._executor.history_reads],
                "start_ns": self._executor.started_ns}

    def start(self, *, request_id: str | None = None,
              deadline_ns: int | None = None) -> InteractionReceipt:
        return self.act(Action("goto", path=self.public.start_path),
                        request_id=request_id, deadline_ns=deadline_ns)

    def observe(self, *, deadline_ns: int | None = None) -> Snapshot:
        if self._finished:
            raise ValueError("session finished")
        self._executor.observe(deadline_ns=deadline_ns)
        snapshot = self._adapter.last_snapshot
        if snapshot is None:
            raise BridgeUnavailable("public snapshot unavailable")
        return snapshot

    def history(self, *, deadline_ns: int | None = None) -> HistoryRead:
        if self._finished:
            raise ValueError("session finished")
        return self._executor.history(deadline_ns=deadline_ns)

    def close(self) -> None:
        """Operator stop; no claim of OS worker/preemption qualification."""
        if not getattr(self, "_closed", False):
            self._adapter.bridge.close_context()
            self._closed = True
        self._finished = True

    def act(self, action: Action, arm: Arm = "R0", *, request_id: str | None = None,
            deadline_ns: int | None = None) -> InteractionReceipt | ExecutionResult:
        if self._finished:
            raise ValueError("session finished")
        validate_action(action)
        snapshot = self._adapter.last_snapshot
        target = None
        if action.kind in {"click", "fill", "select"}:
            if snapshot is None:
                raise ValueError("capture a public snapshot before reference actions")
            target = referenced_target(action, snapshot)
        if action.kind == "click":
            if action.intent is None or target is None:
                raise ValueError("mutation click requires original public intent")
            m = action.intent
            captured = self._executor.capture(m.operation, m.target_id, m.payload,
                                              target, m.before_version)
            result = self._executor.execute(captured, arm, request_id=request_id, deadline_ns=deadline_ns)
            if result.disposition in {"harness_unknown", "cap_abort"}:
                self._finished = True
            return result
        receipt = self._executor.perform(action, request_id=request_id, deadline_ns=deadline_ns)
        if action.kind == "finish" and receipt.status == "acknowledged":
            self._finished = True
        return receipt
