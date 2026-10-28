"""Explicit trusted in-process development embedding; NOT a browser/sandbox.

The canonical browser/IPC bridge remains unjoined. No default backend is added
to BrowserSession or CLI. Authority/driver handles stay on this trusted side.
"""
from html import escape
import json
from typing import Protocol
from uuid import uuid4

from .actions import Action, validate_action
from .browser import BrowserSession, BridgeUnavailable, ContextReceipt, MediaStatus
from .contracts import HistoryRead, Intent, Origin
from .driver import DevelopmentTask
from .executor import Arm, ExecutionResult
from .host import LocalTaskPort
from .ports import ActionReceipt, InteractionReceipt
from .routing import RoutePolicy
from .snapshot import Snapshot, referenced_target


class InProcessDevelopmentBridge:
    """Synchronous accepted task/authority wiring, explicitly convenience-only.

    LocalTaskPort stamps terminal responses after the synchronous task call
    returns, using authority.now_ns(). No browser/client timestamps are used.
    Default local remap installation is never represented as a browser ACK.
    """
    def __init__(self, task: DevelopmentTask):
        self._port = LocalTaskPort(task)
        self.public, self.clock_id = task.public, task.authority.clock_id
        self._policy: RoutePolicy | None = None
        self._context_id: str | None = None
        self._closed = False
        self._url = ""
        self._navigation: list[str] = []
        self._snapshot: Snapshot | None = None
        self._bodies: dict[str, str] = {}

    def now_ns(self) -> int:
        return self._port.now_ns()

    def _check(self, deadline_ns: int) -> None:
        if self._closed or self._context_id is None:
            raise BridgeUnavailable("development context unavailable/closed")
        self._port._check(deadline_ns)

    def open_context(self, policy: RoutePolicy, deadline_ns: int) -> ContextReceipt:
        self._port._check(deadline_ns)
        if self._context_id is not None or self._closed or policy.start_path != self.public.start_path:
            raise BridgeUnavailable("one fresh development namespace per bridge required")
        self._policy = policy
        self._context_id = "embedding-" + uuid4().hex
        self._url = policy.authorize(self.public.start_path, "GET")
        return ContextReceipt(self.public.run_id, self.public.epoch, self.clock_id,
                              self._context_id, True,
                              MediaStatus("unavailable", "unavailable",
                                          "in-process convenience: no browser/media/isolation qualification"),
                              "in_process_convenience")

    def snapshot(self, deadline_ns: int) -> Snapshot:
        self._check(deadline_ns)
        assert self._policy is not None
        if self._url == self._policy.origin + self.public.start_path + "/history":
            read = self._port.history(uuid4().hex, deadline_ns)
            # Ordinary public transitions only, no seal/attempt/fault controls.
            body = json.dumps({"showing_through": read.served_version,
                               "latest": read.latest_version,
                               "transitions": [dict(operation=t.operation, target_id=t.target_id,
                                                    payload=dict(t.payload), state_version=t.state_version)
                                               for t in read.transitions]}, sort_keys=True)
            snapshot = Snapshot(self.public.run_id, self.public.epoch, uuid4().hex,
                                self._url, (), body, read.served_version)
        else:
            page = self._port.observe(deadline_ns)
            markup = page.html
            for control in page.controls:
                value = self._bodies.get(control.row_context, "")
                original = f'<textarea id="{control.ref}" name="body" required></textarea>'
                filled = f'<textarea id="{control.ref}" name="body" required>{escape(value)}</textarea>'
                markup = markup.replace(original, filled)
            # Version remains unknown on the task page. Public history must be
            # obtained separately; never read private DB/version state here.
            snapshot = Snapshot(self.public.run_id, self.public.epoch, page.snapshot_epoch,
                                self._url, page.targets + page.controls, markup)
        self._check(deadline_ns)
        self._snapshot = snapshot
        return snapshot

    def prepare_action(self, request_id: str, deadline_ns: int) -> None:
        self._check(deadline_ns)
        self._port.prepare_action(request_id, deadline_ns)

    def cancel_action(self, request_id: str) -> None:
        self._port.cancel_action(request_id)

    def execute(self, intent: Intent, request_id: str, origin: Origin,
                deadline_ns: int) -> ActionReceipt:
        # LocalTaskPort owns even pre-dispatch deadline cleanup. It returns a
        # bound receipt only after a synchronous task terminal response.
        return self._port.execute(intent, request_id, origin, deadline_ns)

    def history(self, request_id: str, deadline_ns: int) -> HistoryRead:
        self._check(deadline_ns)
        return self._port.history(request_id, deadline_ns)

    def wait(self, duration_ns: int, deadline_ns: int) -> None:
        self._check(deadline_ns)
        self._port.wait(duration_ns, deadline_ns)

    def interact(self, action: Action, request_id: str,
                 deadline_ns: int) -> InteractionReceipt:
        self._check(deadline_ns)
        validate_action(action)
        assert self._policy is not None
        if action.kind == "goto":
            url = self._policy.authorize(action.path, "GET")
            self._navigation.append(self._url)
            self._url, self._snapshot = url, None
        elif action.kind == "back":
            if self._navigation:
                self._url = self._policy.authorize(self._navigation.pop(), "GET")
            self._snapshot = None
        elif action.kind == "reload":
            self._policy.authorize(self._url, "GET")
            self._snapshot = None
        elif action.kind in {"fill", "select"}:
            if self._snapshot is None:
                raise ValueError("capture a public control first")
            target = referenced_target(action, self._snapshot)
            if action.kind != "fill" or target is None or target.name != "Body":
                raise BridgeUnavailable("control is not present in original development HTML")
            self._bodies[target.row_context] = action.value
        elif action.kind == "wait":
            self._port.wait(action.duration_ms * 1_000_000, deadline_ns)
        elif action.kind != "finish":
            raise ValueError("closed non-mutation interaction required")
        self._check(deadline_ns)
        receipt = InteractionReceipt(request_id, self.public.run_id, self.public.epoch,
                                     self.clock_id, self.now_ns(), "acknowledged", self._url)
        if action.kind == "finish":
            self._closed = True
        return receipt

    def close_context(self) -> None:
        # Logical stop only. Never cancels an uncertain issued action or claims
        # OS worker death. The synchronous convenience backend has no subprocess.
        self._closed = True
        self._snapshot = None


def create_development_session(task: DevelopmentTask, origin: str, **limits: int) -> BrowserSession:
    """Operator opt-in factory, never a default canonical browser backend."""
    return BrowserSession(InProcessDevelopmentBridge(task), origin,
                          allow_convenience=True, **limits)


class LoopCodec(Protocol):
    """Explicit accepted D2 mapping hook. No shape compatibility is assumed."""
    def decode_action(self, action: object) -> Action: ...
    def observation(self, snapshot: Snapshot, *, clock_id: str,
                    started_ns: int, completed_ns: int) -> object: ...
    def feedback(self, *, request_id: str, clock_id: str, response_ns: int | None,
                 result: ExecutionResult | InteractionReceipt | None,
                 error: str) -> object: ...


class TrustedActionPortAdapter:
    """Trusted loop adapter preserving exact caller correlation/deadline.

    IDs are correlation inputs validated/bound by the executor, not worker
    authority to select run/epoch/origin/root lineage. Codecs must be explicitly
    installed by trusted composition after producer acceptance. None refuses.
    """
    def __init__(self, session: BrowserSession, codec: LoopCodec | None, *, arm: Arm = "R0"):
        if codec is None:
            raise BridgeUnavailable("accepted D2 observation/action/feedback codec is not bound")
        self._session, self._codec, self._arm = session, codec, arm
        self.clock_id = session.clock_id
        self._started = False
        self._halted = False

    def now_ns(self) -> int:
        return self._session.now_ns()

    def observe(self, deadline_ns: int) -> object:
        if self._halted:
            raise BridgeUnavailable("loop adapter halted; trusted reconciliation required")
        started = self.now_ns()
        if not self._started:
            receipt = self._session.start(deadline_ns=deadline_ns)
            if receipt.status != "acknowledged":
                raise BridgeUnavailable("task start not acknowledged")
            self._started = True
        snapshot = self._session.observe(deadline_ns=deadline_ns)
        completed = self.now_ns()
        if type(deadline_ns) is not int or completed >= deadline_ns:
            self._halted = True
            raise TimeoutError("loop observation deadline exceeded")
        value = self._codec.observation(snapshot, clock_id=self.clock_id,
                                        started_ns=started, completed_ns=completed)
        if self.now_ns() >= deadline_ns:
            self._halted = True
            raise TimeoutError("loop observation encoding deadline exceeded")
        return value

    def execute(self, action: object, *, request_id: str, deadline_ns: int) -> object:
        if self._halted or not self._started:
            raise BridgeUnavailable("loop must observe a fresh task before execution")
        if type(deadline_ns) is not int or self.now_ns() >= deadline_ns:
            raise TimeoutError("absolute loop action deadline required and must remain")
        mapped = validate_action(self._codec.decode_action(action))
        result = None
        response_ns = None
        error = ""
        try:
            result = self._session.act(mapped, self._arm, request_id=request_id,
                                       deadline_ns=deadline_ns)
            response_ns = None
            if isinstance(result, InteractionReceipt):
                if result.request_id != request_id:
                    raise ValueError("feedback request identity mismatch")
                response_ns = result.response_ns
            elif isinstance(result, ExecutionResult):
                if result.request_id != request_id:
                    raise ValueError("feedback correlation mismatch")
                if (result.receipts and not result.uncertain_request_ids
                        and not result.pending_cleanup_request_ids):
                    response_ns = result.receipts[-1].response_ns
                if result.disposition in {"harness_unknown", "cap_abort"}:
                    self._halted = True
            else:
                raise ValueError("unbound dispatch result")
        except Exception as exc:
            self._halted = True
            # No local clock stamp stands in for a missing authority completion.
            response_ns, error = None, type(exc).__name__
        try:
            feedback = self._codec.feedback(request_id=request_id, clock_id=self.clock_id,
                                            response_ns=response_ns, result=result, error=error)
        except Exception as exc:
            self._halted = True
            raise BridgeUnavailable("accepted loop feedback codec unavailable") from exc
        if self.now_ns() >= deadline_ns:
            self._halted = True
            raise TimeoutError("loop action feedback deadline exceeded")
        return feedback
