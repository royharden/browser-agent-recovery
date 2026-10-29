"""Bounded offline actor loop over public ports; no private truth or SDK retry."""
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from typing import Callable, Protocol
from uuid import uuid4

from ..providers import (Action, Limits, ProviderPort, ProviderResult,
                         action_schema, make_request, parse_action)
from ..providers.port import canonical
from .prompts import PromptUnavailable, render_prompt_messages, select_prompt_profile


@dataclass(frozen=True)
class PublicObservation:
    run_id: str
    epoch: str
    clock_id: str
    goal: str
    snapshot_epoch: str
    snapshot_json: str
    allowed_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        for value in (self.run_id, self.epoch, self.clock_id, self.snapshot_epoch):
            if type(value) is not str or not value or len(value) > 256:
                raise ValueError("bounded public identity required")
        if type(self.goal) is not str or not self.goal or len(self.goal.encode()) > 8192:
            raise ValueError("bounded public goal required")
        if type(self.snapshot_json) is not str or len(self.snapshot_json.encode()) > 65536:
            raise ValueError("bounded public snapshot required")
        if canonical(json.loads(self.snapshot_json)) != self.snapshot_json:
            raise ValueError("snapshot must be canonical detached public JSON")
        if type(self.allowed_paths) is not tuple or not self.allowed_paths:
            raise ValueError("immutable public path allowlist required")
        task_path = "/tasks/"+self.run_id
        for path in self.allowed_paths:
            Action("goto", path=path)
            if path != "/history" and path != task_path and not path.startswith(task_path+"/"):
                raise ValueError("path is outside the public task namespace")

    @property
    def digest(self) -> str:
        content = {"run_id": self.run_id, "epoch": self.epoch, "clock_id": self.clock_id,
                   "goal": self.goal, "snapshot_epoch": self.snapshot_epoch,
                   "snapshot": json.loads(self.snapshot_json), "allowed_paths": self.allowed_paths}
        return hashlib.sha256(canonical(content).encode()).hexdigest()


@dataclass(frozen=True)
class ActionFeedback:
    request_id: str
    run_id: str
    epoch: str
    clock_id: str
    response_ns: int
    status: str
    public_message: str = ""

    def __post_init__(self) -> None:
        if any(type(value) is not str or not value or len(value) > 256
               for value in (self.request_id, self.run_id, self.epoch, self.clock_id)):
            raise ValueError("feedback identity required")
        if type(self.response_ns) is not int or self.response_ns < 0:
            raise ValueError("feedback authority clock required")
        if self.status not in {"acknowledged", "failed", "unknown"}:
            raise ValueError("closed feedback status required")
        if type(self.public_message) is not str or len(self.public_message.encode()) > 4096:
            raise ValueError("bounded ordinary feedback required")


class ActionPort(Protocol):
    """Trusted adapter: only ordinary observations and closed literal actions.

    D1 must implement routing, deadline enforcement, step accounting and any
    selected recovery wrapper in its executor. This protocol grants no arbitrary
    JS/HTTP/filesystem/admin action. It is not itself worker isolation.
    """
    clock_id: str

    def now_ns(self) -> int: ...
    def observe(self, deadline_ns: int) -> PublicObservation: ...
    def execute(self, action: Action, *, request_id: str, deadline_ns: int) -> ActionFeedback: ...


@dataclass(frozen=True)
class LoopLimits:
    max_steps: int = 40
    max_model_calls: int = 16
    budget_ns: int = 180_000_000_000

    def __post_init__(self) -> None:
        for value, ceiling in ((self.max_steps, 40), (self.max_model_calls, 16),
                               (self.budget_ns, 180_000_000_000)):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("invalid bounded loop cap")


@dataclass(frozen=True)
class LoopStep:
    request_id: str
    observation_digest: str | None
    provider_result: ProviderResult | None
    feedback: ActionFeedback | None
    error: str = ""


@dataclass(frozen=True)
class LoopResult:
    termination: str
    steps_used: int
    model_calls: int
    attempts: tuple[LoopStep, ...]
    mode: str = "offline_only"


def run_offline(provider: ProviderPort, port: ActionPort, *, model_id: str,
                provider_limits: Limits = Limits(), limits: LoopLimits = LoopLimits(),
                request_id_factory: Callable[[], str] | None = None,
                arm: str = "R0", source_kind: str = "mock", stage: str = "mock",
                cleared_prompt_profiles: frozenset[str] | set[str] | tuple[str, ...] | None = None,
                ) -> LoopResult:
    """No implicit retry. finish is actor termination, never server-truth success.

    Production timeout/isolation enforcement belongs to the trusted adapter;
    an in-process call cannot be forcibly interrupted by this source loop.
    Replay may supply an exact trusted recorded request-ID stream. It must also
    supply matching public observations; no binding is relaxed to make replay fit.
    Existing call signatures remain accepted, but omitted or unavailable external
    prompt clearance returns not_executed before touching provider or action port.
    arm selects instructions only; recovery wrappers remain the executor's job.
    """
    try:
        prompt_profile = select_prompt_profile(arm=arm, source_kind=source_kind,
                                              stage=stage,
                                              cleared_prompt_profiles=cleared_prompt_profiles)
    except PromptUnavailable as exc:
        return LoopResult("not_executed", 0, 0,
                          (LoopStep("", None, None, None, str(exc)),))
    if type(provider_limits) is not Limits or type(limits) is not LoopLimits:
        raise ValueError("closed provider/loop limits required")
    if getattr(provider, "mode", None) not in {"authored_mock", "strict_replay"}:
        raise ValueError("offline loop refuses live/unidentified providers")
    create_id = request_id_factory if request_id_factory is not None else lambda: uuid4().hex
    used = calls = 0
    attempts: list[LoopStep] = []
    ids = set()
    first_identity = None
    last_feedback = ""
    last_now = -1

    def now() -> int:
        nonlocal last_now
        value = port.now_ns()
        if type(value) is not int or value < 0 or value < last_now:
            raise ValueError("invalid/nonmonotonic authority clock")
        last_now = value
        return value

    def result(reason: str) -> LoopResult:
        return LoopResult(reason, used, calls, tuple(attempts))

    try:
        deadline = now()+limits.budget_ns
    except Exception:
        attempts.append(LoopStep("", None, None, None, "initial_clock_failure"))
        return result("harness_unknown")
    while used < limits.max_steps and calls < limits.max_model_calls:
        request_id = ""
        observation = None
        response = None
        feedback = None
        attempt_start = len(attempts)
        try:
            if now() >= deadline:
                return result("deadline")
            request_id = create_id()
            if type(request_id) is not str or not request_id or request_id in ids:
                raise ValueError("fresh trusted request ID required")
            ids.add(request_id)
            used += 1
            observation = port.observe(deadline)
            if type(observation) is not PublicObservation or observation.clock_id != port.clock_id:
                raise ValueError("public observation clock/shape mismatch")
            identity = (observation.run_id, observation.epoch, observation.clock_id, observation.goal)
            if first_identity is None:
                first_identity = identity
            elif identity != first_identity:
                raise ValueError("public task identity changed during loop")
            if now() >= deadline:
                attempts.append(LoopStep(request_id, observation.digest, None, None, "observe_deadline"))
                return result("deadline")
            if used >= limits.max_steps:
                attempts.append(LoopStep(request_id, observation.digest, None, None, "step_cap"))
                return result("cap_abort")
            # Reserve a whole configured provider-call time allowance. Never
            # begin a call when even its stated bound extends past task deadline.
            if now()+provider_limits.deadline_ms*1_000_000 > deadline:
                attempts.append(LoopStep(request_id, observation.digest, None, None, "call_deadline_bound"))
                return result("deadline")
            messages = render_prompt_messages(prompt_profile, observation, last_feedback,
                                              provider_limits, limits)
            expected = make_request(messages, action_schema(), model_id, provider_limits,
                                    request_id=request_id, observation_digest=observation.digest)
            calls += 1
            response = provider.complete(messages, action_schema(), model_id, provider_limits,
                                         request_id=request_id, observation_digest=observation.digest)
            if (type(response) is not ProviderResult or response.request != expected
                    or response.mode != provider.mode):
                raise ValueError("provider request/schema/model/observation binding mismatch")
            if now() >= deadline:
                attempts.append(LoopStep(request_id, observation.digest, response, None, "provider_deadline"))
                return result("deadline")
            output = {"action": None if response.action is None else asdict(response.action),
                      "error": None if response.error is None else asdict(response.error),
                      "raw_usage": response.raw_usage}
            if len(canonical(output).encode()) > provider_limits.max_output_bytes:
                attempts.append(LoopStep(request_id, observation.digest, response, None, "provider_output_cap"))
                return result("provider_error")
            if response.error is not None:
                attempts.append(LoopStep(request_id, observation.digest, response, None, "provider_error"))
                return result("provider_error")
            action = parse_action(response.action)
            if action.duration_ms is not None and action.duration_ms > provider_limits.max_wait_ms:
                attempts.append(LoopStep(request_id, observation.digest, response, None, "action_wait_cap"))
                return result("action_rejected")
            if action.snapshot_epoch is not None and action.snapshot_epoch != observation.snapshot_epoch:
                raise ValueError("action uses a different captured snapshot")
            if action.path is not None and action.path not in observation.allowed_paths:
                raise ValueError("action path outside trusted public allowlist")
            used += 1
            before = now()
            feedback = port.execute(action, request_id=request_id, deadline_ns=deadline)
            completed = now()
            if (type(feedback) is not ActionFeedback
                    or (feedback.request_id, feedback.run_id, feedback.epoch, feedback.clock_id) != (
                        request_id, observation.run_id, observation.epoch, observation.clock_id)
                    or not before <= feedback.response_ns <= completed):
                raise ValueError("action feedback identity/clock mismatch")
            attempts.append(LoopStep(request_id, observation.digest, response, feedback))
            if completed >= deadline:
                return result("deadline")
            if action.operation == "finish":
                # finish is a real interaction, not an unbound model assertion.
                # Unknown/failed completion halts conservatively; never retry
                # a finish that may already have closed the trusted session.
                return result("finished" if feedback.status == "acknowledged" else "harness_unknown")
            # An ordinary failed/uncertain receipt is shown to the actor on its
            # next call. Any later action is a new explicit actor decision, not
            # an implicit SDK/controller retry.
            last_feedback = canonical({"status": feedback.status, "message": feedback.public_message})
        except Exception:
            if len(attempts) == attempt_start:
                attempts.append(LoopStep(request_id, observation.digest if type(observation) is PublicObservation else None,
                                         response if type(response) is ProviderResult else None,
                                         feedback if type(feedback) is ActionFeedback else None,
                                         "closed_port_or_request_failure"))
            else:
                # Preserve the already-recorded result/feedback on a later
                # formatting/return failure, without counting dispatch twice.
                attempts[-1] = replace(attempts[-1], error="closed_port_or_request_failure")
            return result("harness_unknown")
    return result("cap_abort")
