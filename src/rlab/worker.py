"""Bounded public action decoder; no authority/admin imports or executable tools.

The explicit composition entry joins inherited public IPC and the accepted broker
client. Standalone activation refuses; this source does not establish isolation.
"""
import json
from dataclasses import asdict, dataclass
import hashlib
import os
import selectors
import stat
import sys
import threading
import time
from typing import BinaryIO

from .actions import Action, parse_action
from .agents.loop import ActionFeedback, ActionPort, LoopLimits, PublicObservation
from .agents.prompts import render_prompt_messages, select_prompt_profile
from .providers.broker import BrokerClosed, OfflineBroker, REQUEST_FIELDS, REQUEST_VERSION
from .providers.codec import BrokerCodec
from .providers.mock_replay import AuthoredMockProvider, ReplayProvider
from .providers.port import (Limits, action_schema, canonical, make_request,
                             parse_action as parse_provider_action)

MAX_FRAME_BYTES = 16384
MAX_ACTIONS = 40


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def decode_action(frame: bytes) -> Action:
    if type(frame) is not bytes or not 0 < len(frame) <= MAX_FRAME_BYTES:
        raise ValueError("bounded public JSON frame required")
    try:
        value = json.loads(frame.decode("utf-8"), object_pairs_hook=_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("invalid public JSON") from exc
    return parse_action(value)


def read_action(stream: BinaryIO) -> Action:
    """Caller must provide a transport with enforced read deadline/preemption."""
    frame = stream.readline(MAX_FRAME_BYTES + 1)
    if not frame.endswith(b"\n"):
        raise ValueError("bounded newline-terminated frame required")
    return decode_action(frame)


@dataclass(frozen=True)
class InheritedPipe:
    """Operator-installed FIFO capabilities, not paths or worker wire selectors.

    Descriptors must already be nonblocking, dedicated and inherited intentionally.
    Construction validates but never opens, duplicates or changes descriptors.
    Operator retains close/lifetime ownership; endpoint never closes unrelated FDs.
    """
    read_fd: int
    write_fd: int
    owner_uid: int
    codec: BrokerCodec = BrokerCodec()

    def __post_init__(self) -> None:
        if (sys.platform != "linux" or type(self.codec) is not BrokerCodec
                or type(self.owner_uid) is not int or self.owner_uid <= 0
                or self.read_fd == self.write_fd):
            raise ValueError("Linux operator-owned distinct FIFO capabilities required")
        import fcntl  # Linux-only; importing the source on Windows must not open FDs.
        pipe_ids = []
        for fd, mode in ((self.read_fd, os.O_RDONLY), (self.write_fd, os.O_WRONLY)):
            if type(fd) is not int or fd < 3:
                raise ValueError("dedicated inherited pipe FD required")
            info = os.fstat(fd)
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            if (not stat.S_ISFIFO(info.st_mode) or info.st_uid != self.owner_uid
                    or stat.S_IMODE(info.st_mode) & 0o077
                    or flags & os.O_ACCMODE != mode or not flags & os.O_NONBLOCK):
                raise ValueError("owned nonblocking unidirectional FIFO required")
            pipe_ids.append((info.st_dev, info.st_ino))
        if pipe_ids[0] == pipe_ids[1]:
            raise ValueError("separate request and response FIFOs required")

    @staticmethod
    def _ready(fd: int, event: int, deadline_ns: int) -> None:
        if type(deadline_ns) is not int or deadline_ns <= time.monotonic_ns():
            raise TimeoutError("pipe absolute monotonic deadline")
        with selectors.DefaultSelector() as selector:
            selector.register(fd, event)
            while True:
                remaining = deadline_ns - time.monotonic_ns()
                if remaining <= 0:
                    raise TimeoutError("pipe deadline")
                if selector.select(remaining / 1_000_000_000):
                    if time.monotonic_ns() >= deadline_ns:
                        raise TimeoutError("pipe deadline")
                    return

    def _read_exact(self, size: int, deadline_ns: int) -> bytes:
        data = bytearray()
        while len(data) < size:
            self._ready(self.read_fd, selectors.EVENT_READ, deadline_ns)
            try:
                chunk = os.read(self.read_fd, min(4096, size - len(data)))
            except BlockingIOError:
                continue
            if not chunk:
                raise EOFError("inherited pipe closed")
            data.extend(chunk)
        return bytes(data)

    def read_frame(self, deadline_ns: int) -> bytes:
        prefix = self._read_exact(4, deadline_ns)
        size = int.from_bytes(prefix, "big")
        # Inspect exactly four bytes before body read/allocation. Never drain an
        # oversize body: the caller terminally closes acceptance on this failure.
        if not 1 <= size <= self.codec.max_frame_bytes:
            raise ValueError("pipe body prefix exceeds trusted codec cap")
        return prefix + self._read_exact(size, deadline_ns)

    def write_frame(self, frame: bytes, deadline_ns: int) -> None:
        self.codec.decode(frame)  # exact bounded canonical frame before any write
        offset = 0
        while offset < len(frame):
            self._ready(self.write_fd, selectors.EVENT_WRITE, deadline_ns)
            try:
                count = os.write(self.write_fd, memoryview(frame)[offset:offset + 4096])
            except BlockingIOError:
                continue
            if count <= 0:
                raise EOFError("inherited pipe write closed")
            offset += count


@dataclass(frozen=True)
class TrustedPromptConfig:
    """Private immutable operator config; never deserialized from worker frames."""
    model_id: str
    cleared_prompt_profiles: frozenset[str]
    arm: str = "R0"
    source_kind: str = "mock"
    stage: str = "mock"
    provider_limits: Limits = Limits()
    loop_limits: LoopLimits = LoopLimits()
    max_requests: int = 16

    def __post_init__(self) -> None:
        if (type(self.cleared_prompt_profiles) is not frozenset
                or type(self.provider_limits) is not Limits
                or type(self.loop_limits) is not LoopLimits
                or type(self.max_requests) is not int
                or not 1 <= self.max_requests <= self.loop_limits.max_model_calls):
            raise ValueError("fixed bounded trusted prompt configuration required")


class OfflinePipeOwner:
    """Privileged serialized owner; never pass this object/provider to a worker.

    Explicit capture is the sole authorization path. serve_once never authorizes.
    Absolute deadlines must use the authority's Linux monotonic clock domain.
    Pipe deadlines do not hard-preempt a blocking in-process provider or port.
    """
    def __init__(self, endpoint: InheritedPipe,
                 provider: AuthoredMockProvider | ReplayProvider, *,
                 profile: str, config: TrustedPromptConfig):
        if type(endpoint) is not InheritedPipe or type(config) is not TrustedPromptConfig:
            raise ValueError("operator endpoint and fixed config required")
        select_prompt_profile(arm=config.arm, source_kind=config.source_kind,
                              stage=config.stage,
                              cleared_prompt_profiles=config.cleared_prompt_profiles)
        self._endpoint, self._config = endpoint, config
        self._broker = OfflineBroker(provider, model_id=config.model_id, profile=profile,
                                     limits=config.provider_limits, codec=endpoint.codec,
                                     max_requests=config.max_requests)
        self._lock = threading.Lock()
        self._authorized: set[str] = set()
        self._deadlines: dict[str, int] = {}
        self._seen: set[str] = set()
        self._closed = False
        self._identity: tuple[str, str, str] | None = None
        self._last_clock = -1
        self._public_observation: PublicObservation | None = None

    @property
    def closed(self) -> bool:
        return self._closed or self._broker.closed

    def _enter(self) -> None:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("serialized pipe owner required")
        if self.closed:
            self._lock.release()
            raise BrokerClosed("pipe owner closed; stop reading")

    def capture_and_authorize(self, action_port: ActionPort, request_id: str,
                              deadline_ns: int, trusted_previous_feedback: str = "") -> dict:
        self._enter()
        try:
            config = self._config
            # External exact prompt clearance precedes clock/observe/provider.
            prompt = select_prompt_profile(arm=config.arm, source_kind=config.source_kind,
                stage=config.stage, cleared_prompt_profiles=config.cleared_prompt_profiles)
            if (type(request_id) is not str or not 1 <= len(request_id) <= 256
                    or any(ord(c) < 32 for c in request_id)
                    or request_id in self._authorized or request_id in self._seen
                    or len(self._authorized) >= config.max_requests):
                raise ValueError("fresh bounded trusted request identity required")
            now = action_port.now_ns()
            if (type(now) is not int or now < self._last_clock or type(deadline_ns) is not int
                    or not now < deadline_ns <= now + min(config.loop_limits.budget_ns,
                        config.provider_limits.deadline_ms * 1_000_000)):
                raise ValueError("trusted clock/deadline rejected")
            self._last_clock = now
            observation = action_port.observe(deadline_ns)
            if type(observation) is not PublicObservation or observation.clock_id != action_port.clock_id:
                raise ValueError("actual trusted public observation required")
            identity = (observation.run_id, observation.epoch, observation.clock_id)
            if self._identity is not None and identity != self._identity:
                raise ValueError("fresh owner required for another run/epoch/clock")
            messages = render_prompt_messages(prompt, observation, trusted_previous_feedback,
                                               config.provider_limits, config.loop_limits)
            request = make_request(messages, action_schema(), config.model_id, config.provider_limits,
                                   request_id=request_id, observation_digest=observation.digest)
            after = action_port.now_ns()
            if type(after) is not int or not now <= after < deadline_ns:
                raise TimeoutError("observation authorization deadline/clock")
            self._last_clock = after
            self._broker.authorize_request(request)
            self._authorized.add(request_id)
            self._deadlines[request_id] = deadline_ns
            self._identity = identity
            self._public_observation = observation
            # Only public wire data leaves the owner, no ProviderRequest/private object.
            return {"version": REQUEST_VERSION, "request_id": request_id,
                    "observation_digest": observation.digest,
                    "schema_sha256": hashlib.sha256(canonical(action_schema()).encode()).hexdigest(),
                    "messages": json.loads(request.messages_json)}
        finally:
            self._lock.release()

    def serve_once(self, deadline_ns: int) -> None:
        self._enter()
        try:
            frame = self._endpoint.read_frame(deadline_ns)
            try:
                request = self._endpoint.codec.decode(frame)
            except (ValueError, TypeError, RecursionError, UnicodeError, OverflowError):
                # Complete malformed frames still consume the accepted broker's
                # attempt budget. Stop afterward; never resynchronize the stream.
                response = self._broker.handle_frame(frame)
                self._endpoint.write_frame(response, deadline_ns)
                self._closed = True
                return
            request_id = request.get("request_id")
            if type(request_id) is str:
                if not 1 <= len(request_id) <= 256 or request_id in self._seen:
                    raise ValueError("duplicate/rebound worker request identity")
                if len(self._seen) >= self._config.max_requests:
                    raise BrokerClosed("pipe owner request cap")
                self._seen.add(request_id)
            bound_deadline = self._deadlines.get(request_id) if type(request_id) is str else None
            if bound_deadline is not None:
                deadline_ns = min(deadline_ns, bound_deadline)
            if time.monotonic_ns() >= deadline_ns:
                raise TimeoutError("authorized request deadline expired before dispatch")
            response = self._broker.handle_frame(frame)
            # Even the final accepted call may receive its response, then no read.
            self._endpoint.write_frame(response, deadline_ns)
            if self._broker.closed:
                self._closed = True
        except BaseException:
            # Partial frame/write, malformed input or unknown completion cannot be
            # resumed/retried on this byte stream. Operator owns FD disposal.
            self._closed = True
            raise
        finally:
            self._lock.release()


class WorkerPipeClient:
    """Worker gets only this endpoint capability, never a broker/provider owner."""
    def __init__(self, endpoint: InheritedPipe):
        if type(endpoint) is not InheritedPipe:
            raise ValueError("operator-installed pipe endpoint required")
        self._endpoint = endpoint
        self._seen: set[str] = set()
        self._closed = False
        self._lock = threading.Lock()

    def request(self, public_request: dict, deadline_ns: int) -> dict:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("serialized worker endpoint required")
        try:
            if self._closed or len(self._seen) >= 16:
                raise BrokerClosed("worker pipe closed/capped")
            frame = self._endpoint.codec.encode(public_request)
            detached = self._endpoint.codec.decode(frame)
            identity = detached.get("request_id")
            if (set(detached) != REQUEST_FIELDS or detached.get("version") != REQUEST_VERSION
                    or type(identity) is not str or not 1 <= len(identity) <= 256
                    or identity in self._seen):
                raise ValueError("closed fresh public broker request required")
            self._seen.add(identity)
            self._endpoint.write_frame(frame, deadline_ns)
            response = self._endpoint.codec.decode(self._endpoint.read_frame(deadline_ns))
            if (response.get("version") != "rlab.offline.response.v1"
                    or response.get("request_id") != identity
                    or response.get("observation_digest") != detached["observation_digest"]
                    or response.get("schema_sha256") != detached["schema_sha256"]):
                raise ValueError("uncorrelated broker response")
            if time.monotonic_ns() >= deadline_ns:
                raise TimeoutError("worker response decode deadline exceeded")
            return response
        except BaseException:
            self._closed = True
            raise
        finally:
            self._lock.release()


PUBLIC_VERSION = "rlab.worker.public.v1"


def _id(value: object) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 256
            or any(ord(c) < 32 for c in value)):
        raise ValueError("bounded public identity required")
    return value


@dataclass(frozen=True)
class WorkerConfig:
    run_id: str
    epoch: str
    clock_id: str
    limits: LoopLimits = LoopLimits()
    request_timeout_ns: int = 30_000_000_000
    max_wait_ms: int = 5000

    def __post_init__(self) -> None:
        for value in (self.run_id, self.epoch, self.clock_id):
            _id(value)
        if (type(self.limits) is not LoopLimits
                or type(self.request_timeout_ns) is not int
                or not 1 <= self.request_timeout_ns <= 30_000_000_000
                or type(self.max_wait_ms) is not int or not 1 <= self.max_wait_ms <= 10000):
            raise ValueError("closed bounded worker configuration required")


def _observation(raw: dict) -> PublicObservation:
    if type(raw) is not dict or set(raw) != set(PublicObservation.__dataclass_fields__):
        raise ValueError("closed public observation required")
    detached = dict(raw)
    if type(detached["allowed_paths"]) is not list:
        raise ValueError("public path list required")
    detached["allowed_paths"] = tuple(detached["allowed_paths"])
    return PublicObservation(**detached)


class PublicActionPipe:
    """Fixed worker-side public channel. No owner, path or callback dispatch."""
    def __init__(self, endpoint: InheritedPipe):
        if type(endpoint) is not InheritedPipe:
            raise ValueError("operator-installed public FIFO capability required")
        self._endpoint = endpoint
        self._closed = False
        self._lock = threading.Lock()
        self._count = 0

    def exchange(self, operation: str, request_id: str, payload: dict, deadline_ns: int) -> dict:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("serialized public channel required")
        try:
            if self._closed or self._count >= MAX_ACTIONS:
                raise RuntimeError("public channel closed/capped")
            if operation not in {"capture", "execute"}:
                raise ValueError("closed public operation required")
            _id(request_id)
            self._count += 1
            request = {"version": PUBLIC_VERSION, "operation": operation,
                       "request_id": request_id, "payload": payload}
            self._endpoint.write_frame(self._endpoint.codec.encode(request), deadline_ns)
            response = self._endpoint.codec.decode(self._endpoint.read_frame(deadline_ns))
            if (set(response) != {"version", "operation", "request_id", "payload", "error"}
                    or response["version"] != PUBLIC_VERSION
                    or response["operation"] != operation or response["request_id"] != request_id
                    or type(response["payload"]) is not dict):
                raise ValueError("uncorrelated public response")
            if time.monotonic_ns() >= deadline_ns:
                raise TimeoutError("public response decode deadline exceeded")
            if response["error"] is not None:
                # Retain the actual bounded reply at the loop's attempt boundary.
                return response
            return response
        except BaseException:
            self._closed = True
            raise
        finally:
            self._lock.release()


class PublicActionPipeOwner:
    """Privileged composition only: never pass this owner to the worker.

    serve_once's deadline is trusted operator input, never a worker clock field.
    The operator runs this owner and OfflinePipeOwner on their separate channels.
    Public errors are retained; uncertain execution closes rather than retries.
    """
    def __init__(self, endpoint: InheritedPipe, action_port: ActionPort,
                 offline_owner: OfflinePipeOwner, *, config: WorkerConfig):
        if (type(endpoint) is not InheritedPipe or type(offline_owner) is not OfflinePipeOwner
                or type(config) is not WorkerConfig):
            raise ValueError("fixed privileged public composition required")
        self._endpoint, self._port, self._offline = endpoint, action_port, offline_owner
        self._config = config
        self._pending: tuple[str, PublicObservation] | None = None
        self._seen: set[str] = set()
        self._steps = 0
        self._closed = False
        self._last_clock = -1
        self._deadline: int | None = None
        self._lock = threading.Lock()
        self._records: list[tuple[str | None, str | None, str]] = []
        self._feedback = ""

    @property
    def records(self) -> tuple[tuple[str | None, str | None, str], ...]:
        return tuple(self._records)

    def _now(self) -> int:
        now = self._port.now_ns()
        if (type(now) is not int or now < 0 or now < self._last_clock
                or self._port.clock_id != self._config.clock_id):
            raise ValueError("public owner authority clock mismatch")
        self._last_clock = now
        return now

    def serve_once(self, deadline_ns: int) -> None:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("serialized public owner required")
        if self._closed or self._steps >= self._config.limits.max_steps:
            self._closed = True
            self._lock.release()
            raise RuntimeError("public owner closed/capped; stop reading")
        raw = None
        response = None
        try:
            now = self._now()
            if self._deadline is None:
                self._deadline = now + self._config.limits.budget_ns
            if type(deadline_ns) is not int or deadline_ns <= now:
                raise TimeoutError("trusted public deadline required")
            deadline_ns = min(deadline_ns, self._deadline,
                              now + self._config.request_timeout_ns)
            request = self._endpoint.codec.decode(self._endpoint.read_frame(deadline_ns))
            raw = canonical(request)
            if (set(request) != {"version", "operation", "request_id", "payload"}
                    or request["version"] != PUBLIC_VERSION or type(request["payload"]) is not dict):
                raise ValueError("closed public request required")
            identity = _id(request["request_id"])
            operation, payload = request["operation"], request["payload"]
            self._steps += 1
            if operation == "capture":
                if (payload or self._pending is not None or identity in self._seen
                        or len(self._seen) >= self._config.limits.max_model_calls
                        or self._steps >= self._config.limits.max_steps):
                    raise ValueError("fresh bounded capture required")
                self._seen.add(identity)
                # Capture/authorize happens privately, never from worker metadata.
                public_request = self._offline.capture_and_authorize(
                    self._port, identity, deadline_ns, trusted_previous_feedback=self._feedback)
                # The accepted request contains rendered public observation. A
                # second observe could differ, so obtain the exact captured one
                # through the owner capture return slot, not by observing again.
                observation = self._offline._public_observation
                if type(observation) is not PublicObservation or (
                        observation.run_id, observation.epoch, observation.clock_id) != (
                        self._config.run_id, self._config.epoch, self._config.clock_id):
                    raise ValueError("public task identity changed")
                self._pending = (identity, observation)
                result = {"observation": asdict(observation), "public_request": public_request}
            elif operation == "execute":
                if self._pending is None or self._pending[0] != identity or set(payload) != {"action"}:
                    raise ValueError("capture-bound closed action required")
                observation = self._pending[1]
                action = parse_provider_action(payload["action"])
                if ((action.snapshot_epoch is not None and action.snapshot_epoch != observation.snapshot_epoch)
                        or (action.path is not None and action.path not in observation.allowed_paths)
                        or (action.duration_ms is not None and action.duration_ms > self._config.max_wait_ms)):
                    raise ValueError("action outside captured public capability")
                self._pending = None  # consume before potentially uncertain effects
                before = self._now()
                feedback = self._port.execute(action, request_id=identity, deadline_ns=deadline_ns)
                # Retain the actual public completion before fallible final
                # clock/binding checks. A late receipt remains evidence even
                # though it cannot authorize success or another dispatch.
                if type(feedback) is ActionFeedback:
                    response = canonical({"retained_feedback": asdict(feedback)})
                after = self._now()
                if (type(feedback) is not ActionFeedback
                        or (feedback.request_id, feedback.run_id, feedback.epoch, feedback.clock_id) != (
                            identity, observation.run_id, observation.epoch, observation.clock_id)
                        or not before <= feedback.response_ns <= after < deadline_ns):
                    raise ValueError("public feedback binding/deadline mismatch")
                result = {"feedback": asdict(feedback)}
                self._feedback = canonical({"status": feedback.status, "message": feedback.public_message})
                if action.operation == "finish":
                    self._closed = True
            else:
                raise ValueError("closed public operation required")
            if self._now() >= deadline_ns:
                raise TimeoutError("public operation deadline")
            response = canonical({"version": PUBLIC_VERSION, "operation": operation,
                                  "request_id": identity, "payload": result, "error": None})
            self._endpoint.write_frame(self._endpoint.codec.encode(json.loads(response)), deadline_ns)
            self._records.append((raw, response, ""))
        except BaseException as exc:
            self._closed = True
            self._records.append((raw, response, type(exc).__name__ + ": " + str(exc)[:4096]))
            raise
        finally:
            self._lock.release()


@dataclass(frozen=True)
class WorkerCapabilities:
    broker: WorkerPipeClient
    public: PublicActionPipe

    def __post_init__(self) -> None:
        if type(self.broker) is not WorkerPipeClient or type(self.public) is not PublicActionPipe:
            raise ValueError("exact inherited worker public capabilities required")
        endpoints = (self.broker._endpoint, self.public._endpoint)
        descriptors = [fd for endpoint in endpoints for fd in (endpoint.read_fd, endpoint.write_fd)]
        if len(set(descriptors)) != 4:
            raise ValueError("separate broker and public descriptors required")
        pipes = [(os.fstat(fd).st_dev, os.fstat(fd).st_ino) for fd in descriptors]
        if len(set(pipes)) != 4:
            raise ValueError("separate broker and public FIFO streams required")


@dataclass(frozen=True)
class WorkerAttempt:
    request_id: str
    observation_json: str | None = None
    broker_response_json: str | None = None
    public_response_json: str | None = None
    error: str = ""


@dataclass(frozen=True)
class WorkerResult:
    termination: str
    steps_used: int
    model_calls: int
    attempts: tuple[WorkerAttempt, ...]
    qualification: str = "source-composition-runtime-unverified"


def main(config: WorkerConfig | None = None,
         capabilities: WorkerCapabilities | None = None) -> WorkerResult:
    """Fixed operator composition, not a launcher or isolation attestation.

    No environment/CLI descriptor selectors or actor callback loader. Canonical
    privileged activation must still pass SourceProfile's unavailable gate.
    """
    if type(config) is not WorkerConfig or type(capabilities) is not WorkerCapabilities:
        raise RuntimeError("worker activation refused: operator inherited capabilities absent; isolation unqualified")
    attempts: list[WorkerAttempt] = []
    used = calls = 0
    last_now = -1

    def now() -> int:
        nonlocal last_now
        current = time.monotonic_ns()
        if type(current) is not int or current < 0 or current < last_now:
            raise ValueError("worker monotonic clock rejected")
        last_now = current
        return current

    def result(reason: str) -> WorkerResult:
        return WorkerResult(reason, used, calls, tuple(attempts))

    try:
        deadline = now() + config.limits.budget_ns
    except Exception as exc:
        attempts.append(WorkerAttempt("", error=type(exc).__name__ + ": " + str(exc)[:4096]))
        return result("harness_unknown")
    while used + 2 <= config.limits.max_steps and calls < config.limits.max_model_calls:
        identity = "w_" + hashlib.sha256(
            canonical([config.run_id, config.epoch, config.clock_id]).encode()).hexdigest() + f"_{calls + 1}"
        observation_json = broker_json = public_json = None
        try:
            current = now()
            if current >= deadline:
                return result("deadline")
            call_deadline = min(deadline, current + config.request_timeout_ns)
            used += 1
            capture = capabilities.public.exchange("capture", identity, {}, call_deadline)
            public_json = canonical(capture)
            if capture["error"] is not None or set(capture["payload"]) != {"observation", "public_request"}:
                raise ValueError("public capture failed")
            observation = _observation(capture["payload"]["observation"])
            observation_json = canonical(capture["payload"]["observation"])
            if (observation.run_id, observation.epoch, observation.clock_id) != (
                    config.run_id, config.epoch, config.clock_id):
                raise ValueError("worker observation identity mismatch")
            request = capture["payload"]["public_request"]
            if (type(request) is not dict or request.get("request_id") != identity
                    or request.get("observation_digest") != observation.digest):
                raise ValueError("public capture broker binding mismatch")
            calls += 1  # count dispatch even when completion is unknown
            response = capabilities.broker.request(request, call_deadline)
            broker_json = canonical(response)
            if response.get("ok") is not True or type(response.get("result")) is not dict:
                attempts.append(WorkerAttempt(identity, observation_json, broker_json, public_json, "broker_error"))
                return result("provider_error")
            action = parse_provider_action(response["result"].get("action"))
            if ((action.snapshot_epoch is not None and action.snapshot_epoch != observation.snapshot_epoch)
                    or (action.path is not None and action.path not in observation.allowed_paths)
                    or (action.duration_ms is not None and action.duration_ms > config.max_wait_ms)):
                raise ValueError("action outside captured public capability")
            if now() >= call_deadline:
                raise TimeoutError("worker broker deadline")
            used += 1
            action_wire = {key: value for key, value in asdict(action).items() if value is not None}
            reply = capabilities.public.exchange("execute", identity, {"action": action_wire}, call_deadline)
            public_json = canonical(reply)
            if reply["error"] is not None or set(reply["payload"]) != {"feedback"}:
                raise ValueError("public execute failed")
            feedback_raw = reply["payload"]["feedback"]
            if type(feedback_raw) is not dict or set(feedback_raw) != set(ActionFeedback.__dataclass_fields__):
                raise ValueError("closed feedback required")
            feedback = ActionFeedback(**feedback_raw)
            if ((feedback.request_id, feedback.run_id, feedback.epoch, feedback.clock_id) != (
                    identity, config.run_id, config.epoch, config.clock_id)
                    or not current <= feedback.response_ns <= now() < call_deadline):
                raise ValueError("worker feedback binding/deadline mismatch")
            attempts.append(WorkerAttempt(identity, observation_json, broker_json, public_json))
            if action.operation == "finish":
                return result("finished" if feedback.status == "acknowledged" else "harness_unknown")
        except Exception as exc:
            attempts.append(WorkerAttempt(identity, observation_json, broker_json, public_json, type(exc).__name__ + ": " + str(exc)[:4096]))
            return result("deadline" if isinstance(exc, TimeoutError) else "harness_unknown")
    return result("cap_abort")


if __name__ == "__main__":
    # No standalone capability bootstrap: privileged launch/isolation is unjoined.
    main()
