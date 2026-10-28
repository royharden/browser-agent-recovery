"""Private original-development backend SOURCE; no import-time execution.

Canonical Linux/browser hooks are unavailable. Explicit convenience runs reuse
the authority and public scripted session; they do not qualify isolation, real
DOM installation, research freezing, independent truth or model performance.
"""
from __future__ import annotations

from dataclasses import asdict, fields
import importlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence
from uuid import uuid4

from .cli import AdmissionPort, FixtureRequest, PortResult


class DevelopmentOrchestrationPort(Protocol):
    """D3-owned schedule/runner seam; no default schedule or truth producer."""
    def matrix(self, request: FixtureRequest) -> PortResult: ...
    def freeze(self, request: FixtureRequest) -> PortResult: ...


class JoinedDevelopmentOrchestration:
    """Explicit trusted embedding of D3's actual facade and frozen inputs.

    No default inputs, admission, private specs or schedule are manufactured.
    The caller retains returned artifacts exclusively within its private boundary.
    """
    def __init__(self, *, inputs: dict, admission: Any, port: Any):
        self._inputs, self._admission, self._port = _detached(inputs), admission, port

    def matrix(self, request: FixtureRequest) -> PortResult:
        if request.profile != "in_process_convenience":
            return PortResult("unavailable", "Canonical Linux/browser hooks unavailable")
        try:
            facade = _matrix_types()
        except (ImportError, ValueError, AttributeError, TypeError):
            return PortResult("unavailable", "Accepted D3 provenance runner unavailable; nothing executed")
        artifact = facade.run_matrix(self._inputs, admission=self._admission, port=self._port)
        return PortResult("complete", "Private D3 lifecycle envelope; runtime unverified", artifact)

    def freeze(self, request: FixtureRequest) -> PortResult:
        return PortResult("unavailable", "No independently admitted source-freeze producer installed")


def _matrix_types() -> Any:
    """Only the fixed, separately installed D3 facade may supply wire types."""
    facade = importlib.import_module("evaluation.matrix_runner")
    if "provenance" not in {field.name for field in fields(facade.SealedRun)}:
        raise ValueError("D3 rich provenance facade unjoined")
    return facade


def _detached(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def _provider_receipt(value: Any) -> dict:
    """Normalize only exact accepted immutable producer types, never plugins."""
    from .providers.port import Action, Cost, Limits, ProviderError, ProviderRequest, ProviderResult

    def limits(item: Any) -> dict:
        if type(item) is not Limits:
            raise TypeError("accepted provider Limits required")
        return {"max_messages": item.max_messages, "max_input_bytes": item.max_input_bytes,
                "max_output_bytes": item.max_output_bytes, "deadline_ms": item.deadline_ms,
                "max_wait_ms": item.max_wait_ms}

    def cost(item: Any) -> dict | None:
        if item is None:
            return None
        if type(item) is not Cost:
            raise TypeError("accepted provider Cost required")
        return {"state": item.state, "amount_decimal": item.amount_decimal, "currency": item.currency}

    request = value.request if type(value) is ProviderResult else None
    if type(value) is not ProviderResult or (request is not None and type(request) is not ProviderRequest):
        raise TypeError("accepted ProviderResult/request required")
    request_json = None if request is None else {
        "messages_json": request.messages_json, "action_schema_json": request.action_schema_json,
        "model_id": request.model_id, "limits": limits(request.limits),
        "request_id": request.request_id, "observation_digest": request.observation_digest}
    action = value.action
    if action is not None and type(action) is not Action:
        raise TypeError("accepted provider Action required")
    action_json = None if action is None else {
        "operation": action.operation, "ref": action.ref, "snapshot_epoch": action.snapshot_epoch,
        "value": action.value, "path": action.path, "duration_ms": action.duration_ms}
    error = value.error
    if error is not None and type(error) is not ProviderError:
        raise TypeError("accepted ProviderError required")
    if (type(value.timings) is not tuple or any(type(pair) is not tuple or len(pair) != 2
            or type(pair[0]) is not str or type(pair[1]) is not int for pair in value.timings)):
        raise TypeError("immutable provider timing pairs required")
    return {"request": request_json, "action": action_json,
            "error": None if error is None else {"code": error.code, "message": error.message,
                                                  "retryable": error.retryable},
            "raw_usage_json": value.raw_usage_json, "provider_request_id": value.provider_request_id,
            "actual_model_id": value.actual_model_id, "timings": [[key, stamp] for key, stamp in value.timings],
            "current_cost": cost(value.current_cost), "source_cost": cost(value.source_cost),
            "attempt_index": value.attempt_index, "mode": value.mode,
            "rejected_response_json": value.rejected_response_json}


def _loop_receipt(value: Any) -> dict:
    from .agents.loop import ActionFeedback, LoopResult, LoopStep
    if type(value) is not LoopResult or type(value.attempts) is not tuple:
        raise TypeError("accepted immutable LoopResult required")
    steps = []
    for step in value.attempts:
        if type(step) is not LoopStep:
            raise TypeError("accepted LoopStep required")
        feedback = step.feedback
        if feedback is not None and type(feedback) is not ActionFeedback:
            raise TypeError("accepted ActionFeedback required")
        steps.append({"request_id": step.request_id, "observation_digest": step.observation_digest,
                      "provider_result": None if step.provider_result is None else _provider_receipt(step.provider_result),
                      "feedback": None if feedback is None else {
                          "request_id": feedback.request_id, "run_id": feedback.run_id, "epoch": feedback.epoch,
                          "clock_id": feedback.clock_id, "response_ns": feedback.response_ns,
                          "status": feedback.status, "public_message": feedback.public_message},
                      "error": step.error})
    return {"termination": value.termination, "steps_used": value.steps_used,
            "model_calls": value.model_calls, "attempts": steps, "mode": value.mode}


def _current_cost(attempts: list[dict], *, complete: bool) -> dict:
    """Current receipt accounting only; source/replay costs never enter spend."""
    unknown = {"state": "unknown", "known_usd": None, "unresolved_usd": None}
    if not complete or not attempts:
        return unknown
    costs = [attempt["current_cost"] for attempt in attempts]
    if all(cost["state"] == "known_zero" for cost in costs):
        return {"state": "known_zero", "known_usd": "0", "unresolved_usd": "0"}
    # Supplied accounting is not a billing verification. Unsupported currency,
    # unknown usage/cost or unbounded decimal text preserves unknown accounting.
    from decimal import Decimal, InvalidOperation, localcontext
    total = Decimal(0)
    try:
        with localcontext() as context:
            context.prec = 512
            for cost in costs:
                if cost["state"] == "known_zero":
                    continue
                amount = cost["amount_decimal"]
                if (cost["state"] != "known" or cost["currency"] != "USD"
                        or type(amount) is not str or len(amount) > 128):
                    return unknown
                number = Decimal(amount)
                if not number.is_finite() or number < 0 or abs(number.adjusted()) > 128:
                    return unknown
                total += number
    except (InvalidOperation, ValueError, TypeError):
        return unknown
    return {"state": "known", "known_usd": str(total), "unresolved_usd": "0"}


class _StartedSession:
    """Public-only actor facade; reset's actual start is reused, never repeated."""
    def __init__(self, session: Any, start: Any, deadline_ns: int):
        self._session, self._start, self._deadline = session, start, deadline_ns
        self.public, self.clock_id = session.public, session.clock_id

    def now_ns(self) -> int:
        return self._session.now_ns()

    @property
    def context_receipt(self) -> Any:
        return self._session.context_receipt

    def _end(self, deadline_ns: int | None) -> int:
        if deadline_ns is not None and (type(deadline_ns) is not int or deadline_ns < 0):
            raise ValueError("absolute caller deadline required")
        return min(self._deadline, self._deadline if deadline_ns is None else deadline_ns)

    def start(self, *, deadline_ns: int | None = None) -> Any:
        if self.now_ns() >= self._end(deadline_ns):
            raise TimeoutError("reset start receipt expired")
        return self._start

    def observe(self, *, deadline_ns: int | None = None) -> Any:
        return self._session.observe(deadline_ns=self._end(deadline_ns))

    def history(self, *, deadline_ns: int | None = None) -> Any:
        return self._session.history(deadline_ns=self._end(deadline_ns))

    def act(self, action: Any, arm: str = "R0", *, request_id: str | None = None,
            deadline_ns: int | None = None) -> Any:
        return self._session.act(action, arm, request_id=request_id,
                                 deadline_ns=self._end(deadline_ns))


class DevelopmentMatrixPort:
    """Operator-owned one-row lifecycle, never a competing matrix scheduler.

    Authority is externally created once and retained across rows, preserving the
    deadline clock. The adapter does not own or close that authority. Factories
    receive only public row selectors, never evaluator private specifications.
    Admission must be externally verified and bound to D3's complete input digest.
    """
    offline_only = True

    def __init__(self, authority: Any, *, admission: Any = None,
                 profile: str = "canonical", cleared_prompt_profiles: tuple[str, ...] = (),
                 provider_factory: Callable[[dict], Any] | None = None,
                 action_port_factory: Callable[[Any, dict, int], Any] | None = None,
                 provider_limits: Any = None):
        self._authority, self._admission, self._profile = authority, admission, profile
        self.clock_id = authority.clock_id
        self._clearance = tuple(cleared_prompt_profiles)
        self._provider_factory, self._action_factory = provider_factory, action_port_factory
        self._provider_limits = provider_limits
        self._active: dict | None = None
        self._halted = False

    def now_ns(self) -> int:
        if self._authority.clock_id != self.clock_id:
            raise ValueError("authority clock changed")
        value = self._authority.now_ns()
        if type(value) is not int or value < 0:
            raise ValueError("invalid authority clock")
        return value

    @staticmethod
    def _selection(row: dict) -> tuple[dict, dict]:
        if type(row) is not dict or set(row) != {"schedule", "metadata"}:
            raise ValueError("closed public row and metadata required")
        return row["schedule"], row["metadata"]

    def preflight(self, row: dict, config: dict) -> Any:
        # Importing this operator facade never constructs authority/task/provider.
        facade = importlib.import_module("evaluation.matrix_runner")
        schedule, meta = self._selection(row)
        reason = None
        admission = self._admission
        if self._halted or self._active is not None:
            reason = "backend_cleanup_or_lifecycle_unavailable"
        elif (not isinstance(admission, facade.VerifiedAdmission)
              or admission.state != "PASS"
              or admission.input_sha256 != config.get("matrix_input_sha256")):
            reason = "external_admission_missing_failed_or_input_mismatch"
        elif self._profile != "in_process_convenience":
            reason = "canonical_linux_browser_hooks_unavailable"
        elif any(type(config.get(key)) is not int or not 1 <= config[key] <= ceiling
                 for key, ceiling in (("max_actions", 40), ("max_probes", 40),
                                      ("max_model_calls", 16), ("run_timeout_ns", 180_000_000_000))):
            reason = "explicit_bounded_operation_limits_required"
        elif "provenance" not in {field.name for field in fields(facade.SealedRun)}:
            reason = "D3_rich_provenance_facade_unjoined"
        elif (schedule.get("family") not in {"F1", "F2", "F3"}
              or schedule.get("mode") != "fixture"
              or schedule.get("arm") not in {"R0", "R1", "R2", "R3", "R23"}
              or schedule.get("condition") not in {"clean", "EXPIRED_VIEW", "STALE_ID", "INTERRUPTED_ACTION"}
              or meta.get("actor") != "profile-default"
              or meta.get("parser") != "standard"
              or meta.get("configuration") != "standard"):
            reason = "requested_actor_parser_or_configuration_unavailable"
        elif (type(meta.get("seed")) is not int or not 0 <= meta["seed"] <= 999
              or type(meta.get("lag_ns")) is not int or meta["lag_ns"] not in {0, 2_000_000_000}
              or type(meta.get("reconcile_budget_ns")) is not int
              or meta["reconcile_budget_ns"] not in {1_000_000_000, 4_000_000_000}):
            reason = "requested_development_selector_unavailable"
        elif schedule.get("source_kind") not in {"scripted", "mock", "authored"}:
            reason = "offline_source_unavailable"
        elif schedule["source_kind"] != "scripted":
            if self._provider_factory is None or self._action_factory is None or self._provider_limits is None:
                reason = "explicit_offline_provider_action_port_or_limits_unavailable"
            else:
                try:
                    from .agents.session_codec import SessionLoopCodec
                except ImportError:
                    return facade.UnattemptedRun(schedule["schedule_id"], "accepted_session_codec_unavailable")
                if not isinstance(SessionLoopCodec, type):
                    return facade.UnattemptedRun(schedule["schedule_id"], "accepted_session_codec_unavailable")
                from .agents.prompts import PromptUnavailable, select_prompt_profile
                from .providers import Limits
                if type(self._provider_limits) is not Limits:
                    return facade.UnattemptedRun(schedule["schedule_id"], "accepted_provider_limits_required")
                try:
                    select_prompt_profile(arm=schedule["arm"], source_kind=schedule["source_kind"],
                                          stage="mock" if schedule["source_kind"] == "mock" else "keyless",
                                          cleared_prompt_profiles=self._clearance)
                except PromptUnavailable as exc:
                    reason = str(exc)
        return facade.UnattemptedRun(schedule["schedule_id"], reason) if reason else None

    @staticmethod
    def _deadline(config: dict, deadline_ns: int) -> int:
        deadlines = [deadline_ns, config["run_deadline_ns"], config["matrix_deadline_ns"]]
        if any(type(value) is not int or value < 0 for value in deadlines):
            raise ValueError("absolute same-clock deadlines required")
        return min(deadlines)

    def reset(self, row: dict, config: dict) -> Any:
        previous = self._active
        try:
            return self._reset(row, config)
        except Exception:
            # D3 cannot close a lease that reset failed to return. Retain the
            # attempted state, halt permanently, and stop any constructed context.
            if previous is None and self._active is not None:
                self._halted = True
                session = self._active.get("session")
                if session is not None:
                    session.close()
                    self._active["stopped"] = True
            raise

    def _reset(self, row: dict, config: dict) -> Any:
        refused = self.preflight(row, config)
        if refused is not None:
            raise ValueError("reset refused: " + refused.reason)
        facade = _matrix_types()
        schedule, meta = self._selection(row)
        deadline = self._deadline(config, config["run_deadline_ns"])
        from .driver import DevelopmentTask
        from .faults import FaultPlan
        from .lag import HistoryLag
        from .trusted_bridge import create_development_session
        if self.now_ns() >= deadline:
            raise TimeoutError("reset deadline exhausted")
        # Latch attempted ownership before any task/context construction. A failed
        # reset remains halted until trusted cleanup can establish logical stop.
        self._halted = True
        self._active = {"lease": None, "task": None, "session": None, "stopped": False}
        task = DevelopmentTask(self._authority, schedule["family"], meta["seed"],
                               fault=None if schedule["condition"] == "clean" else FaultPlan(schedule["condition"]),
                               lag=HistoryLag(meta["lag_ns"]))
        self._active["task"] = task
        started_ns = self.now_ns()
        session = create_development_session(
            task, "http://127.0.0.1:20000", max_actions=config["max_actions"],
            max_probes=config["max_probes"], run_budget_ns=config["run_timeout_ns"],
            reconciliation_budget_ns=meta["reconcile_budget_ns"], absolute_deadline_ns=deadline)
        self._active["session"] = session
        start = session.start(deadline_ns=deadline)
        context = session.context_receipt
        if (start.status != "acknowledged" or context is None or context.fresh is not True
                or context.clock_id != self.clock_id or self.now_ns() >= deadline):
            raise ValueError("fresh acknowledged context unavailable")
        lease = facade.RunLease(schedule["schedule_id"], task.public.run_id, task.public.epoch,
                                self.clock_id, task.public.start_path, context.context_id)
        self._active.update(lease=lease, row=_detached(row), config=_detached(config),
                            start=start, started_ns=started_ns, deadline=deadline, executed=False)
        self._halted = False
        return lease

    def execute(self, lease: Any, row: dict, config: dict, deadline_ns: int) -> Any:
        facade = _matrix_types()
        active = self._active
        if (self._halted or active is None or active["lease"] != lease or active["executed"]
                or row != active["row"] or config != active["config"]):
            raise ValueError("single exact reset/row execution required")
        deadline = min(active["deadline"], self._deadline(config, deadline_ns))
        if self.now_ns() >= deadline:
            raise TimeoutError("execute deadline exhausted")
        active["executed"] = True
        session = active["session"]
        public = _StartedSession(session, active["start"], deadline)
        schedule, _ = self._selection(row)
        source = schedule["source_kind"]
        outcome, provider, error, seal = None, None, None, None
        provenance = {"schema": "rlab.run-provenance.v1", "source_kind": source,
                      "state": "unknown", "provider_attempts": None, "loop": None,
                      "reason": "execution did not produce complete receipts"}
        cost = {"state": "unknown", "known_usd": None, "unresolved_usd": None}
        termination, calls = "harness_unknown", None
        try:
            if source == "scripted":
                from .scripted import run_scripted
                outcome = run_scripted(public, schedule["arm"])
                termination = outcome.status
                calls = 0
                provenance.update(state="not_applicable", provider_attempts=[], loop=None,
                                  reason="public scripted actor made no provider call")
            else:
                from .agents.loop import LoopLimits, run_offline
                provider = self._provider_factory(_detached(row))
                if provider.attempts != ():
                    raise ValueError("fresh per-row provider attempt ledger required")
                port = self._action_factory(public, _detached(row), deadline)
                if port.clock_id != self.clock_id or getattr(provider, "mode", None) not in {"authored_mock", "strict_replay"}:
                    raise ValueError("bound offline provider/action port required")
                remaining = deadline - self.now_ns()
                outcome = run_offline(provider, port, model_id=schedule["model"],
                                      provider_limits=self._provider_limits,
                                      limits=LoopLimits(config["max_actions"], config["max_model_calls"], remaining),
                                      arm=schedule["arm"], source_kind=source,
                                      stage="mock" if source == "mock" else "keyless",
                                      cleared_prompt_profiles=self._clearance)
                termination, calls = outcome.termination, outcome.model_calls
        except Exception as exc:
            error = type(exc).__name__
        finally:
            # Never seal an actor context that may still be active.
            try:
                session.close()
                active["stopped"] = True
                seal = self._authority.seal(active["task"].public)
            except Exception as exc:
                error = error or type(exc).__name__
                self._halted = True
        if provider is not None:
            try:
                attempts = []
                provenance["provider_attempts"] = attempts
                ledger = provider.attempts
                if type(ledger) is not tuple:
                    raise TypeError("immutable accepted provider ledger required")
                provider_results = []
                for result in ledger:
                    raw = _provider_receipt(result)
                    provider_results.append(raw)
                    attempts.append({**raw, "binding": raw.get("request"),
                                     "raw_usage": raw.get("raw_usage_json"),
                                     "rejected_response": raw.get("rejected_response_json")})
                loop = None if outcome is None else _loop_receipt(outcome)
                provenance["loop"] = loop
                returned = [] if loop is None else [step["provider_result"] for step in loop["attempts"]
                                                    if step["provider_result"] is not None]
                complete = (loop is not None and returned == provider_results
                            and len(returned) == loop["model_calls"] == len(attempts) == calls)
                if complete:
                    provenance.update(state="recorded", reason=None)
                else:
                    provenance["reason"] = "provider_loop_execution_attempt_coverage_mismatch"
                cost = _current_cost(attempts, complete=complete)
            except Exception as exc:
                error = error or type(exc).__name__
                provenance.update(state="unknown", reason="receipt_normalization_failed:" + type(exc).__name__)
        try:
            receipt = session.execution_receipt()
        except Exception as exc:
            receipt = {"actions": None, "reads": []}
            error = error or type(exc).__name__
        if source == "scripted" and outcome is not None:
            disposition = getattr(getattr(outcome, "action_result", None), "disposition", None)
            if (outcome.status != "authored" or disposition == "harness_unknown"
                    or getattr(outcome.finish_receipt, "status", None) != "acknowledged"):
                error = error or "incomplete_scripted_receipt"
        if source != "scripted" and (outcome is None or outcome.termination in {"not_executed", "harness_unknown"}):
            error = error or "attempted_loop_unknown"
        if error or seal is None or self.now_ns() > deadline:
            termination, seal, self._halted = "harness_unknown", None, True
        record = {"seal": seal, "spec": None,
                  "execution": {"run_id": lease.run_id, "epoch": lease.epoch, "clock_id": lease.clock_id,
                                "start_ns": active["started_ns"], "termination": termination,
                                "actions": receipt["actions"], "model_calls": calls,
                                "failures": [error] if error else []},
                  "cost": cost, "reads": receipt["reads"], "media": []}
        return facade.SealedRun(lease.schedule_id, lease, _detached(record), _detached(provenance))

    def close(self, lease: Any) -> None:
        active = self._active
        if active is None or active["lease"] != lease:
            self._halted = True
            raise ValueError("exact active lease required for close")
        try:
            if not active["stopped"]:
                active["session"].close()
                active["stopped"] = True
            if not active["executed"]:
                self._halted = True
            self._active = None
        except Exception:
            self._halted = True
            raise


def _private_root(path: Path | None) -> Path:
    if path is None or not path.is_absolute():
        raise ValueError("explicit absolute private DB root required")
    # Reject links/junctions at every existing component, including ancestors.
    # A private operator-controlled root/ACL is still required against races.
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("linked private roots are refused")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir() or any("onedrive" in part.casefold() for part in resolved.parts):
        raise ValueError("existing private root outside OneDrive required")
    product = Path(__file__).resolve().parents[2]
    if resolved == product or product in resolved.parents:
        raise ValueError("private root must be outside product source")
    return resolved


def _write(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")


class DevelopmentBackend:
    """Trusted operator object; never pass it or private outputs to an actor.

    Inputs are external anchors, never reconstructed from receipt identities.
    The admission producer remains injected until its accepted source joins.
    """
    def __init__(
        self, *, admission: AdmissionPort | None = None,
        document: Mapping[str, Any] | None = None,
        expected_hashes: Mapping[str, str] | None = None,
        builder_ids: Sequence[str] = (), trusted_ids: Sequence[str] = (),
        db_root: Path | None = None,
        orchestration: DevelopmentOrchestrationPort | None = None,
    ):
        self._admission = admission
        self._document = document
        self._expected_hashes = dict(expected_hashes or {})
        self._builder_ids, self._trusted_ids = tuple(builder_ids), tuple(trusted_ids)
        self._db_root, self._orchestration = db_root, orchestration

    def _gate(self) -> PortResult | None:
        if (self._admission is None or self._document is None
                or not self._expected_hashes or not self._builder_ids or not self._trusted_ids):
            return PortResult("pending", "Genuine external admission inputs/producer missing; nothing executed")
        decision = self._admission.admit(
            self._document, expected_hashes=self._expected_hashes,
            builder_ids=self._builder_ids, trusted_ids=self._trusted_ids,
        )
        if decision.state == "PASS":
            return None
        if decision.state == "FAIL":
            return PortResult("failed", "External admission FAIL; all execution modes skipped")
        if decision.state == "PENDING":
            return PortResult("pending", "External admission PENDING; nothing executed")
        raise ValueError("invalid admission state")

    @staticmethod
    def _validate(request: FixtureRequest) -> None:
        if (request.task not in {"F1", "F2", "F3"}
                or request.policy not in {"R0", "R1", "R2", "R3", "R23"}
                or request.profile not in {"canonical", "in_process_convenience"}
                or request.condition not in {"clean", "EXPIRED_VIEW", "STALE_ID", "INTERRUPTED_ACTION"}
                or request.mode != "fixture"):
            raise ValueError("closed development selection required")
        for value, low, high in ((request.seed, 0, 999), (request.max_actions, 1, 40),
                                 (request.max_probes, 1, 40),
                                 (request.horizon_ns, 1, 180_000_000_000)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError("development caps outside closed bounds")
        if type(request.lag_ns) is not int or request.lag_ns not in {0, 2_000_000_000}:
            raise ValueError("operator history lag must be 0 or 2 seconds")

    def matrix(self, request: FixtureRequest) -> PortResult:
        blocked = self._gate()
        if blocked is not None:
            return blocked
        self._validate(request)
        if self._orchestration is None:
            return PortResult("unavailable", "D3 matrix runner seam unjoined; nothing scheduled or executed")
        return self._orchestration.matrix(request)

    def freeze(self, request: FixtureRequest) -> PortResult:
        blocked = self._gate()
        if blocked is not None:
            return blocked
        self._validate(request)
        if self._orchestration is None:
            return PortResult("unavailable", "D3 source-schedule seam unjoined; no research freeze or independent receipt")
        return self._orchestration.freeze(request)

    def run(self, request: FixtureRequest) -> PortResult:
        blocked = self._gate()
        if blocked is not None:
            return blocked
        self._validate(request)
        if request.profile == "canonical":
            return PortResult("unavailable", "Canonical Linux/browser hooks unavailable; nothing executed")
        root = _private_root(self._db_root)
        # All runtime modules are lazy and strictly downstream of real admission.
        from .authority import Authority
        from .driver import DevelopmentTask
        from .faults import FaultPlan
        from .lag import HistoryLag
        from .scripted import run_scripted
        from .trusted_bridge import create_development_session

        directory = root / ("development-" + uuid4().hex)
        directory.mkdir(mode=0o700, exist_ok=False)
        if directory.resolve(strict=True).parent != root:
            raise ValueError("private run containment failure")
        database = directory / "authority.sqlite3"
        # Reserve exclusively before SQLite opens; never reopen an existing run.
        with database.open("xb"):
            pass
        authority = None
        session = None
        task = None
        outcome = None
        stopped = False
        executed = False
        error = ""
        seal = None
        try:
            authority = Authority(database)
            task = DevelopmentTask(
                authority, request.task, request.seed,
                fault=None if request.condition == "clean" else FaultPlan(request.condition),
                lag=HistoryLag(request.lag_ns),
            )
            session = create_development_session(
                task, "http://127.0.0.1:20000", max_actions=request.max_actions,
                max_probes=request.max_probes, run_budget_ns=request.horizon_ns,
            )
            if not callable(getattr(session, "close", None)):
                raise ValueError("logical session stop hook unavailable")
            executed = True
            outcome = run_scripted(session, request.policy)
        except Exception as exc:
            error = type(exc).__name__
        finally:
            try:
                if session is not None:
                    session.close()
                    stopped = True
                else:
                    # No actor session was created; no worker was launched.
                    stopped = True
                if authority is not None and task is not None and stopped:
                    seal = authority.seal(task.public)
                    _write(directory / "seal.json", seal)
            except Exception as exc:
                error = error or type(exc).__name__
            finally:
                if authority is not None:
                    try:
                        authority.close()
                    except Exception as exc:
                        error = error or type(exc).__name__
        disposition = getattr(getattr(outcome, "action_result", None), "disposition", None)
        unknown = (bool(error) or not stopped or seal is None or outcome is None
                   or outcome.status != "authored" or disposition == "harness_unknown"
                   or getattr(outcome.finish_receipt, "status", None) != "acknowledged")
        record = {
            "schema": "rlab.development-record.v1", "selection": asdict(request),
            "execution": "unknown" if unknown else "returned",
            "attempted": executed, "error_type": error or None,
            "outcome": None if outcome is None else asdict(outcome),
            "logical_session_stopped": stopped, "os_worker": "not_launched",
            "profile": "in_process_convenience", "sandbox": "unqualified",
            "model_measurement": "not_yet_measured", "oracle": "unqualified",
            "scorer_truth": "not_supplied", "validation": "runtime_unverified",
            "current_call_cost": {"state": "unknown", "amount": None,
                                  "basis": "no_provider_cost_receipt"},
            "media": {"trace": "not_requested", "video": "not_requested"},
            "private_seal": "seal.json" if seal is not None else None,
        }
        _write(directory / "record.json", record)
        return PortResult("failed" if unknown else "complete",
                          "Private authored development record; no oracle/model/isolation acceptance",
                          {"private_directory": str(directory), "execution": record["execution"]})
