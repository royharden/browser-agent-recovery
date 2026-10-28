"""Fixed operator-only browser/authority IPC consumer; no transport discovery.

The preinstalled capability must authenticate its peer, frame bounded typed
messages, preempt deadlines, and source timestamps from the authority clock.
This consumer implements the application protocol, not that privileged launch.
Nothing in this module reads browser headers, forms or client clocks as lineage.
"""
from dataclasses import dataclass
import threading
from typing import Literal, Protocol

from .actions import text
from .contracts import HistoryRead, Intent, Origin, PublicTask
from .ports import ActionReceipt, InteractionReceipt
from .snapshot import Snapshot, validate_snapshot


Operation = Literal["clock", "prepare", "installed", "cancel", "bind", "completed", "history", "interaction"]


@dataclass(frozen=True)
class BrowserRequest:
    operation: Operation
    run_id: str
    epoch: str
    clock_id: str
    request_id: str
    root_intent_id: str
    deadline_ns: int
    payload: object = None


@dataclass(frozen=True)
class BrowserResponse:
    operation: Operation
    run_id: str
    epoch: str
    clock_id: str
    request_id: str
    root_intent_id: str
    authority_ns: int
    payload: object = None


@dataclass(frozen=True)
class PreparedRender:
    """Public replacement projection, never a fault label/private schedule."""
    installation_id: str
    snapshot: Snapshot | None


@dataclass(frozen=True)
class InstalledRender:
    installation_id: str
    snapshot: Snapshot | None


@dataclass(frozen=True)
class BoundSubmission:
    intent: Intent
    origin: Origin


@dataclass(frozen=True)
class PublicInteraction:
    url: str
    status: Literal["acknowledged", "unknown"]
    error: str = ""


class OperatorBrowserChannel(Protocol):
    """An inherited operator capability; never actor-selectable path/endpoint.

    bind installs trusted server-side IntentContext out of band for exactly one
    next POST on this browser context. completed waits for its terminal server
    receipt even when browser navigation timed out. installed acknowledges only
    an actually compared DOM projection. history returns ordinary lagged public
    history, not a private event log. All calls are bounded by the implementation.
    """
    def exchange(self, request: BrowserRequest) -> BrowserResponse: ...


class BrowserAuthorityIPC:
    def __init__(self, public: PublicTask, clock_id: str,
                 channel: OperatorBrowserChannel):
        self.public, self.clock_id, self._channel = public, text(clock_id, "clock", 160), channel
        self._last_ns = -1

    def call(self, operation: Operation, request_id: str, deadline_ns: int,
             payload: object = None, *, root: str = "") -> BrowserResponse:
        if operation not in {"clock", "prepare", "installed", "cancel", "bind", "completed", "history", "interaction"}:
            raise ValueError("closed browser IPC operation required")
        text(request_id, "IPC request", 160)
        text(root, "root intent", 160, empty=True)
        if type(deadline_ns) is not int or deadline_ns < 0:
            raise ValueError("absolute authority deadline required")
        request = BrowserRequest(operation, self.public.run_id, self.public.epoch,
                                 self.clock_id, request_id, root, deadline_ns, payload)
        result = self._channel.exchange(request)
        if (type(result) is not BrowserResponse or
                (result.operation, result.run_id, result.epoch, result.clock_id,
                 result.request_id, result.root_intent_id) !=
                (operation, request.run_id, request.epoch, self.clock_id, request_id, root)
                or type(result.authority_ns) is not int or result.authority_ns < self._last_ns):
            raise ValueError("unbound or regressing browser IPC receipt")
        self._last_ns = result.authority_ns
        if result.authority_ns < 0 or (operation not in {"clock", "cancel", "completed"}
                                      and result.authority_ns >= deadline_ns):
            raise TimeoutError("authority IPC deadline exceeded")
        return result

    def now_ns(self) -> int:
        return self.call("clock", "authority-clock", 0).authority_ns

    def prepare(self, request_id: str, deadline_ns: int) -> PreparedRender:
        value = self.call("prepare", request_id, deadline_ns).payload
        if type(value) is not PreparedRender:
            raise ValueError("typed prepare projection required")
        text(value.installation_id, "installation", 160)
        if value.snapshot is not None:
            validate_snapshot(value.snapshot, self.public.run_id, self.public.epoch)
        return value

    def history(self, request_id: str, deadline_ns: int) -> HistoryRead:
        result = self.call("history", request_id, deadline_ns)
        read = result.payload
        if (type(read) is not HistoryRead or
                (read.run_id, read.epoch, read.clock_id, read.request_id) !=
                (self.public.run_id, self.public.epoch, self.clock_id, request_id)
                or type(read.started_ns) is not int or type(read.completed_ns) is not int
                or not 0 <= read.started_ns <= read.completed_ns <= result.authority_ns
                or read.completed_ns >= deadline_ns):
            raise ValueError("unbound ordinary history receipt")
        return read

    def completion(self, intent: Intent, request_id: str, deadline_ns: int) -> ActionReceipt:
        result = self.call("completed", request_id, deadline_ns, root=intent.root_intent_id)
        value = result.payload
        if (type(value) is not ActionReceipt or
                (value.run_id, value.epoch, value.clock_id, value.request_id) !=
                (self.public.run_id, self.public.epoch, self.clock_id, request_id)
                or type(value.response_ns) is not int
                or not 0 <= value.response_ns <= result.authority_ns
                or value.status not in {"acknowledged", "failed", "unchanged", "unknown"}):
            raise ValueError("unbound terminal action receipt")
        return value

    def interaction(self, request_id: str, deadline_ns: int,
                    public: PublicInteraction) -> InteractionReceipt:
        result = self.call("interaction", request_id, deadline_ns, public)
        value = result.payload
        if (type(value) is not InteractionReceipt or
                (value.run_id, value.epoch, value.clock_id, value.request_id) !=
                (self.public.run_id, self.public.epoch, self.clock_id, request_id)
                or value.url != public.url or value.status != public.status
                or type(value.response_ns) is not int
                or not 0 <= value.response_ns <= result.authority_ns):
            raise ValueError("unbound interaction receipt")
        return value

class InheritedBrowserFrames(Protocol):
    """Operator-preinstalled authenticated byte capability with real preemption.

    The capability returns exactly one length-prefixed response frame. It is
    supplied by trusted composition, never opened from an actor path/FD number.
    Clock requests carry deadline 0: the installed capability must impose its
    own bounded control-call timeout for this fixed operation.
    """
    def exchange_frame(self, frame: bytes, deadline_ns: int) -> bytes: ...


class FramedBrowserChannel:
    """Concrete fixed JSON/length-frame consumer; no dynamic type/plugin loader."""
    MAX_FRAME = 131072

    def __init__(self, capability: InheritedBrowserFrames):
        self._capability = capability
        self._lock = threading.Lock()
        self._closed = False

    def exchange(self, request: BrowserRequest) -> BrowserResponse:
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("serialized browser receipt channel required")
        try:
            if self._closed:
                raise RuntimeError("browser receipt channel closed")
            return self._exchange(request)
        except BaseException:
            self._closed = True
            raise
        finally:
            self._lock.release()

    def _exchange(self, request: BrowserRequest) -> BrowserResponse:
        from dataclasses import asdict
        import json
        from .contracts import Target, Transition

        def closed(value: object, fields: set[str]) -> dict:
            if type(value) is not dict or set(value) != fields:
                raise ValueError("closed browser IPC record required")
            return value

        def unique(pairs: list) -> dict:
            value = dict(pairs)
            if len(value) != len(pairs):
                raise ValueError("duplicate IPC field")
            return value

        def target(value: object) -> Target:
            return Target(**closed(value, {"ref", "snapshot_epoch", "role", "name", "row_context"}))

        def snapshot(value: object) -> Snapshot | None:
            if value is None:
                return None
            raw = closed(value, {"run_id", "epoch", "snapshot_epoch", "url", "targets", "body", "served_version"})
            if type(raw["targets"]) is not list or len(raw["targets"]) > 64:
                raise ValueError("IPC target cap")
            return Snapshot(**{**raw, "targets": tuple(target(t) for t in raw["targets"])})

        encoded = json.dumps(asdict(request), ensure_ascii=True, allow_nan=False,
                             separators=(",", ":")).encode("ascii")
        if len(encoded) > self.MAX_FRAME:
            raise ValueError("browser request frame cap")
        frame = self._capability.exchange_frame(len(encoded).to_bytes(4, "big") + encoded,
                                                request.deadline_ns)
        if (type(frame) is not bytes or not 4 <= len(frame) <= self.MAX_FRAME + 4
                or int.from_bytes(frame[:4], "big") != len(frame) - 4):
            raise ValueError("invalid browser response frame")
        raw = closed(json.loads(frame[4:].decode("utf-8"), object_pairs_hook=unique,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite IPC"))),
                     {"operation", "run_id", "epoch", "clock_id", "request_id", "root_intent_id", "authority_ns", "payload"})
        body = raw["payload"]
        if request.operation == "prepare":
            body = closed(body, {"installation_id", "snapshot"})
            body = PreparedRender(body["installation_id"], snapshot(body["snapshot"]))
        elif request.operation == "completed":
            body = ActionReceipt(**closed(body, {"request_id", "run_id", "epoch", "clock_id", "response_ns", "status", "error"}))
        elif request.operation == "interaction":
            body = InteractionReceipt(**closed(body, {"request_id", "run_id", "epoch", "clock_id", "response_ns", "status", "url", "error"}))
        elif request.operation == "history":
            body = closed(body, {"run_id", "epoch", "clock_id", "request_id", "started_ns", "completed_ns", "served_version", "latest_version", "transitions", "successful", "complete", "unfiltered", "cached", "aliases"})
            if type(body["transitions"]) is not list or len(body["transitions"]) > 4096:
                raise ValueError("history transition cap")
            transitions = []
            for entry in body["transitions"]:
                entry = closed(entry, {"operation", "target_id", "payload", "state_version"})
                pairs = entry["payload"]
                if (type(pairs) is not list or len(pairs) > 8
                        or any(type(p) is not list or len(p) != 2
                               or any(type(v) is not str for v in p) for p in pairs)
                        or entry["operation"] not in {"order", "ticket", "delete"}
                        or type(entry["target_id"]) is not str
                        or type(entry["state_version"]) is not int or entry["state_version"] < 0):
                    raise ValueError("invalid public transition")
                transitions.append(Transition(**{**entry, "payload": tuple(tuple(p) for p in pairs)}))
            if (any(type(body[k]) is not bool for k in ("successful", "complete", "unfiltered", "cached", "aliases"))
                    or any(body[k] is not None and (type(body[k]) is not int or body[k] < 0)
                           for k in ("served_version", "latest_version"))):
                raise ValueError("invalid ordinary history metadata")
            body = HistoryRead(**{**body, "transitions": tuple(transitions)})
        elif body is not None:
            raise ValueError("unexpected IPC acknowledgment payload")
        return BrowserResponse(**{**raw, "payload": body})
