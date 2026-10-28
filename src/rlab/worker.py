"""Bounded public action decoder; no authority/admin imports or executable tools.

This worker entry point refuses execution until a real public IPC transport joins
the trusted executor. Decoder construction is not a sandbox or live actor loop.
"""
import json
from dataclasses import dataclass
import hashlib
import os
import selectors
import stat
import sys
import threading
import time
from typing import BinaryIO

from .actions import Action, parse_action
from .agents.loop import ActionPort, LoopLimits, PublicObservation
from .agents.prompts import render_prompt_messages, select_prompt_profile
from .providers.broker import BrokerClosed, OfflineBroker, REQUEST_FIELDS, REQUEST_VERSION
from .providers.codec import BrokerCodec
from .providers.mock_replay import AuthoredMockProvider, ReplayProvider
from .providers.port import Limits, action_schema, canonical, make_request

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


def main() -> int:
    # No stdin loop without a bounded transport and fresh isolated context.
    raise RuntimeError("worker activation refused: public IPC, enforcement and browser context unjoined")


if __name__ == "__main__":
    raise SystemExit(main())
