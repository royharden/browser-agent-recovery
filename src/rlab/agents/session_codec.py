"""Explicit public Session/loop record join; no authority or scorer access.

Implements trusted_bridge.LoopCodec structurally without importing that privileged
module. Missing final completion raises a typed halt, never a fabricated time.
"""
from dataclasses import dataclass
import re
from typing import Callable, NoReturn, TypeGuard

from ..actions import Action, Mutation
from ..contracts import PublicTask
from ..executor import ExecutionResult, Step
from ..ports import ActionReceipt, InteractionReceipt
from ..providers import Action as ProviderAction, parse_action
from ..snapshot import Snapshot
from .loop import ActionFeedback, PublicObservation
from .mapping import map_action, observation_from_snapshot


@dataclass(frozen=True)
class CodecDiagnostic:
    code: str
    request_id: str | None
    detail: str
    dispatch_ids: tuple[str, ...] = ()


class SessionCodecUnavailable(RuntimeError):
    """Operator must stop/reconcile; no ActionFeedback completion was invented."""
    def __init__(self, diagnostic: CodecDiagnostic):
        self.diagnostic = diagnostic
        super().__init__(diagnostic.code+": "+diagnostic.detail)


@dataclass(frozen=True)
class ObservationStamp:
    run_id: str
    epoch: str
    clock_id: str
    snapshot_epoch: str
    started_ns: int
    completed_ns: int


def _time(value: object) -> TypeGuard[int]:
    return type(value) is int and value >= 0


def _request(value: object) -> TypeGuard[str]:
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) is not None


class SessionLoopCodec:
    """One serialized trusted session. Mutation resolver is OPERATOR configuration.

    The resolver receives only the original provider action and captured public
    observation; it must use original goal/action fields, never hidden outcomes.
    It is not a worker-selected handler or an authorization/OS isolation boundary.
    """
    def __init__(self, public: PublicTask, allowed_paths: tuple[str, ...],
                 mutation_resolver: Callable[[ProviderAction, PublicObservation], Mutation], *, clock_id: str):
        if type(public) is not PublicTask or not callable(mutation_resolver):
            raise ValueError("trusted public task and explicit public Mutation resolver required")
        if (type(clock_id) is not str or not clock_id or len(clock_id) > 256
                or any(ord(char) < 32 for char in clock_id)):
            raise ValueError("trusted authority clock identity required")
        routes = {public.start_path, public.start_path+"/history"}
        if (type(allowed_paths) is not tuple or not allowed_paths
                or any(type(path) is not str or path not in routes for path in allowed_paths)):
            raise ValueError("exact public task GET routes required")
        self._public, self._paths, self._resolver = public, allowed_paths, mutation_resolver
        self._clock_id = clock_id
        self._last_observation: PublicObservation | None = None
        self._observations: list[ObservationStamp] = []
        self._diagnostics: list[CodecDiagnostic] = []
        self._halted = False

    @property
    def diagnostics(self) -> tuple[CodecDiagnostic, ...]:
        return tuple(self._diagnostics)

    @property
    def observation_stamps(self) -> tuple[ObservationStamp, ...]:
        return tuple(self._observations)

    def _active(self) -> None:
        if self._halted:
            raise SessionCodecUnavailable(self._diagnostics[-1])

    def _unavailable(self, code: str, request_id: str | None, detail: str,
                     dispatch_ids: tuple[str, ...] = ()) -> NoReturn:
        diagnostic = CodecDiagnostic(code, request_id if _request(request_id) else None, detail, dispatch_ids)
        self._diagnostics.append(diagnostic)
        self._halted = True
        raise SessionCodecUnavailable(diagnostic)

    def decode_action(self, action: object) -> Action:
        self._active()
        if self._last_observation is None:
            self._unavailable("observation_missing", None, "Capture a bound public snapshot before action mapping")
        try:
            source = parse_action(action)
            if source.snapshot_epoch is not None and source.snapshot_epoch != self._last_observation.snapshot_epoch:
                raise ValueError("action did not cite captured snapshot")
            if source.path is not None and source.path not in self._paths:
                raise ValueError("navigation outside configured public routes")
            mutation = self._resolver(source, self._last_observation) if source.operation == "click" else None
            return map_action(source, mutation=mutation)
        except Exception as error:
            self._unavailable("action_mapping_unavailable", None,
                              "Original public action/Mutation mapping refused: "+type(error).__name__)

    def observation(self, snapshot: Snapshot, *, clock_id: str,
                    started_ns: int, completed_ns: int) -> PublicObservation:
        self._active()
        if (clock_id != self._clock_id or not _time(started_ns) or not _time(completed_ns)
                or completed_ns < started_ns
                or (self._observations and started_ns < self._observations[-1].completed_ns)):
            self._unavailable("observation_identity_timing", None, "Trusted observation interval/clock is unavailable")
        try:
            value = observation_from_snapshot(snapshot, self._public, clock_id=clock_id,
                                              allowed_paths=self._paths)
        except Exception as error:
            self._unavailable("observation_mapping_unavailable", None,
                              "Public snapshot mapping refused: "+type(error).__name__)
        self._observations.append(ObservationStamp(self._public.run_id, self._public.epoch,
                                                   clock_id, value.snapshot_epoch, started_ns, completed_ns))
        self._last_observation = value
        return value

    def _receipt(self, receipt: ActionReceipt | InteractionReceipt, request_id: str | None = None, *,
                 correlation_id: str | None = None) -> None:
        if (not isinstance(receipt, (ActionReceipt, InteractionReceipt))
                or not _request(receipt.request_id)
                or (request_id is not None and receipt.request_id != request_id)
                or (receipt.run_id, receipt.epoch, receipt.clock_id) != (
                    self._public.run_id, self._public.epoch, self._clock_id)
                or not _time(receipt.response_ns)
                or type(receipt.status) is not str
                or receipt.status not in {"acknowledged", "failed", "unchanged", "unknown"}):
            self._unavailable("receipt_identity_timing", correlation_id or request_id,
                              "Trusted receipt identity/status/time mismatch")

    def feedback(self, *, request_id: str, clock_id: str, response_ns: int | None,
                 result: ExecutionResult | InteractionReceipt | None, error: str) -> ActionFeedback:
        self._active()
        if (not _request(request_id) or clock_id != self._clock_id or self._last_observation is None
                or type(error) is not str or len(error) > 256):
            self._unavailable("feedback_identity", request_id, "Feedback caller/clock/observation unavailable")
        if error:
            self._unavailable("adapter_error", request_id, "Trusted adapter halted: "+error)
        if not _time(response_ns):
            self._unavailable("completion_missing", request_id, "No trusted terminal action response timestamp")
        if response_ns < self._observations[-1].completed_ns:
            self._unavailable("completion_precedes_observation", request_id, "Completion predates captured public observation")
        if isinstance(result, InteractionReceipt):
            self._receipt(result, request_id)
            if response_ns != result.response_ns or result.status not in {"acknowledged", "unknown"}:
                self._unavailable("interaction_completion", request_id, "Interaction completion is not bound")
            status = result.status
            message = "interaction status="+status
        elif isinstance(result, ExecutionResult):
            if (type(result.receipts) is not tuple or not result.receipts
                    or any(not isinstance(receipt, ActionReceipt) for receipt in result.receipts)
                    or type(result.steps) is not tuple
                    or any(type(ids) is not tuple for ids in (result.pending_cleanup_request_ids,
                           result.uncertain_request_ids, result.cancelled_request_ids))):
                self._unavailable("dispatch_trace_missing", request_id, "Final dispatch receipt/trace missing or malformed")
            dispatch_ids = tuple(receipt.request_id for receipt in result.receipts
                                 if isinstance(receipt, ActionReceipt) and _request(receipt.request_id))
            if (result.request_id != request_id or not _request(result.root_intent_id)
                    or type(result.arm) is not str or result.arm not in {"R0", "R1", "R2", "R3", "R23"}
                    or type(result.disposition) is not str
                    or result.disposition not in {"acknowledged", "committed", "returned", "abstained"}
                    or result.pending_cleanup_request_ids or result.uncertain_request_ids
                    or result.cancelled_request_ids):
                self._unavailable("dispatch_incomplete", request_id,
                                  "Unsafe disposition, cancelled/pending/uncertain completion", dispatch_ids)
            mutations = []
            previous = self._observations[-1].completed_ns
            for step in result.steps:
                if (type(step) is not Step or not _time(step.started_ns) or not _time(step.completed_ns)
                        or not previous <= step.started_ns <= step.completed_ns
                        or type(step.kind) is not str
                        or step.kind not in {"prepare", "observe", "history", "wait", "mutation"}
                        or not _request(step.request_id) or type(step.origin) is not str
                        or step.origin not in {"agent_direct", "controller_retry", "controller_resolve"}
                        or type(step.outcome) is not str or not step.outcome):
                    self._unavailable("dispatch_trace_timing", request_id, "Dispatch trace interval mismatch", dispatch_ids)
                previous = step.completed_ns
                if step.kind == "mutation":
                    mutations.append(step)
            if len(mutations) != len(result.receipts) or len(set(dispatch_ids)) != len(dispatch_ids):
                self._unavailable("final_dispatch_unbound", request_id,
                                  "A dispatch lacks its own receipt; earlier receipt cannot stand in", dispatch_ids)
            for index, (receipt, step) in enumerate(zip(result.receipts, mutations)):
                self._receipt(receipt, correlation_id=request_id)
                if (step.request_id != receipt.request_id
                        or (index == 0 and receipt.request_id != request_id)
                        or not step.started_ns <= receipt.response_ns <= step.completed_ns
                        or step.outcome != receipt.status):
                    self._unavailable("dispatch_receipt_mismatch", request_id, "Receipt does not match issued trace", dispatch_ids)
            final = result.receipts[-1]
            if response_ns != final.response_ns:
                self._unavailable("final_completion_mismatch", request_id, "Provided completion is not final dispatch time", dispatch_ids)
            if result.disposition == "acknowledged" and final.status != "acknowledged":
                self._unavailable("acknowledgement_mismatch", request_id, "No acknowledged final dispatch", dispatch_ids)
            status = final.status if final.status in {"acknowledged", "failed"} else "unknown"
            message = "controller disposition="+result.disposition+"; final dispatch status="+final.status
        else:
            self._unavailable("completion_unavailable", request_id, "No bound dispatch or interaction result")
        return ActionFeedback(request_id, self._public.run_id, self._public.epoch,
                              self._clock_id, response_ns, status, message)
