"""Explicit operator compositions; construction activates no browser or server.

In-process task and browser-peer conveniences are labelled separately. Neither
establishes authenticated transport, OS isolation or hard preemption. No default
backend is added to BrowserSession or CLI; privileged handles remain operator-only.
"""
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
import json
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from .actions import Action, Mutation, validate_action
from .browser import BrowserSession, BridgeUnavailable, ContextReceipt, MediaStatus
from .contracts import HistoryRead, Intent, Origin
from .driver import DevelopmentTask
from .executor import Arm, ExecutionResult
from .host import LocalTaskPort
from .media_capture import MediaCapturePolicy
from .ports import ActionReceipt, InteractionReceipt
from .routing import RoutePolicy
from .snapshot import Snapshot, referenced_target, validate_snapshot

if TYPE_CHECKING:
    from .browser_receipt_peer import BrowserReceiptPeer
    from .playwright_bridge import PlaywrightBridge


class BoundBrowserPeerHTTP:
    """Operator-only WSGI application for exactly one already bound peer.

    Mount this application only on the operator's matching HTTP context. This
    concrete dispatch callsite never chooses authority from environ, headers,
    cookies or forms. Mounting/authenticating the listener remains external.
    """
    def __init__(self, peer: "BrowserReceiptPeer", context_capability: object):
        if context_capability is None:
            raise BridgeUnavailable("explicit operator context capability required")
        self._peer, self._capability = peer, context_capability

    def __call__(self, environ, start_response):
        return self._peer.dispatch_http(self._capability, environ, start_response)


@dataclass(frozen=True)
class BrowserPeerComposition:
    """Trusted operator handles; never serialize/pass this bundle to a worker."""
    session: BrowserSession
    peer: "BrowserReceiptPeer"
    bridge: "PlaywrightBridge"
    http_dispatcher: BoundBrowserPeerHTTP
    profile: str = "browser_peer_in_process"


def create_browser_peer_composition(task: DevelopmentTask, origin: str, *,
                                    context_capability: object,
                                    control_timeout_ns: int = 1_000_000_000,
                                    max_requests: int = 4096,
                                    media_policy: MediaCapturePolicy | None = None,
                                    **session_limits: int) -> BrowserPeerComposition:
    """Fixed opt-in in-process framed peer/browser composition, source only.

    Construction starts no browser/listener or HTTP exchange. BrowserSession
    initializes its controller budget through one in-process framed authority
    clock bootstrap; constructing this composition is therefore execution.
    The supplied capability is an explicit operator choice, not authentication.
    Framing exercises the fixed protocol in process; this is distinctly labelled
    convenience wiring, never a preauthenticated inherited-channel profile.

    The observer reads the actual Playwright document without IPC reentry while
    the peer owns its serialized lock. The recorder is called by PlaywrightBridge
    after an actual ordinary browser operation; an IPC interaction status query
    cannot invoke it. HTTP effects terminate through this peer's real TaskHost
    receipt sink. External HTTP mounting/context authentication, browser/runtime
    activation, supervision and isolation still require separate qualification.
    """
    if context_capability is None:
        raise BridgeUnavailable("explicit operator context capability required")
    if type(max_requests) is not int or not 1 <= max_requests <= 4096:
        raise ValueError("bounded retained interaction cap required")
    if "allow_convenience" in session_limits:
        raise ValueError("browser-peer convenience profile is fixed by composition")
    from .browser_ipc import BrowserAuthorityIPC, FramedBrowserChannel, PublicInteraction
    from .browser_receipt_peer import BrowserReceiptPeer
    from .playwright_bridge import PlaywrightBridge

    # Immutable metadata returned by the actual producer, not a task/authority
    # store. The peer owns lifecycle reservations and its primary retained ledger.
    retained: dict[str, InteractionReceipt] = {}

    def installed_snapshot() -> Snapshot:
        # Bound below before any operation can execute. project_snapshot must be
        # DOM-only: no authority clock, IPC request or nested peer lock acquisition.
        return bridge.project_snapshot()

    def interaction_receipt(request_id: str) -> InteractionReceipt | None:
        return retained.get(request_id)

    peer = BrowserReceiptPeer(task, origin, context_capability=context_capability,
                              installed_snapshot=installed_snapshot,
                              interaction_receipt=interaction_receipt,
                              control_timeout_ns=control_timeout_ns,
                              max_requests=max_requests)

    def record_interaction(request_id: str, public: PublicInteraction) -> InteractionReceipt:
        if request_id in retained or len(retained) >= max_requests:
            raise BridgeUnavailable("retained actual interaction ledger full/reused")
        receipt = peer.record_interaction(context_capability, request_id, public)
        retained[request_id] = receipt
        return receipt

    ipc = BrowserAuthorityIPC(peer.public, peer.clock_id, FramedBrowserChannel(peer))
    bridge = PlaywrightBridge(ipc, record_interaction=record_interaction,
                               profile="browser_peer_in_process", media_policy=media_policy)
    session = BrowserSession(bridge, origin, allow_convenience=True, **session_limits)
    return BrowserPeerComposition(session, peer, bridge,
                                  BoundBrowserPeerHTTP(peer, context_capability))


class _PublicForms(HTMLParser):
    """Parse ordinary captured form fields only; no expected-effect lookup."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms: list[tuple[set[str], dict[str, str]]] = []
        self.buttons: set[str] | None = None
        self.fields: dict[str, str] = {}
        self.textarea: str | None = None

    def _field(self, name: str, value: str) -> None:
        if name in {"ref", "snapshot"}:
            return
        if (name not in {"quantity", "body"} or name in self.fields
                or len(value) > 4096):
            raise ValueError("unsupported/duplicate public form field")
        self.fields[name] = value

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if len(attributes) != len(attrs):
            raise ValueError("duplicate public form attributes")
        if tag == "form":
            if self.buttons is not None:
                raise ValueError("nested public forms refused")
            self.buttons, self.fields = set(), {}
        elif self.buttons is not None:
            if tag == "button" and attributes.get("id"):
                self.buttons.add(attributes["id"])
            elif tag == "input" and attributes.get("name"):
                self._field(attributes["name"], attributes.get("value") or "")
            elif tag == "textarea" and attributes.get("name"):
                self._field(attributes["name"], "")
                self.textarea = attributes["name"]

    def handle_data(self, data: str) -> None:
        if self.textarea is not None:
            value = self.fields[self.textarea] + data
            if len(value) > 4096:
                raise ValueError("public textarea cap")
            self.fields[self.textarea] = value

    def handle_endtag(self, tag: str) -> None:
        if tag == "textarea":
            self.textarea = None
        elif tag == "form" and self.buttons is not None:
            self.forms.append((self.buttons, self.fields))
            self.buttons, self.fields = None, {}


class OriginalPublicMutationResolver:
    """Capture the ACTOR's selected public row and literal form state.

    This does not select the row requested by the goal or consult private truth.
    A wrong native click remains wrong; only R3/R23 fresh semantic guards act.
    """
    def __init__(self, session: BrowserSession):
        self._session = session
        self._snapshot: Snapshot | None = None
        self._deadline: int | None = None
        self._fields: dict[tuple[str, str], str] = {}

    def observe(self, snapshot: Snapshot) -> None:
        self._snapshot = validate_snapshot(snapshot, self._session.public.run_id,
                                          self._session.public.epoch)

    def begin(self, deadline_ns: int) -> None:
        if type(deadline_ns) is not int or deadline_ns < 0:
            raise ValueError("absolute mutation capture deadline required")
        self._deadline = deadline_ns

    def applied(self, action: Action) -> None:
        if action.kind in {"fill", "select"} and self._snapshot is not None:
            target = referenced_target(action, self._snapshot)
            if target is not None:
                self._fields[(target.row_context, target.name)] = action.value

    def __call__(self, provider_action: object, observation: object) -> Mutation | None:
        if (self._snapshot is None
                or getattr(observation, "run_id", None) != self._session.public.run_id
                or getattr(observation, "epoch", None) != self._session.public.epoch
                or getattr(observation, "clock_id", None) != self._session.clock_id
                or getattr(observation, "snapshot_epoch", None) != self._snapshot.snapshot_epoch):
            raise BridgeUnavailable("codec observation differs from original trusted snapshot")
        if getattr(provider_action, "operation", None) != "click":
            return None
        if self._snapshot is None or self._deadline is None:
            raise BridgeUnavailable("original public snapshot/deadline unavailable")
        action = Action("click", ref=getattr(provider_action, "ref", ""),
                        snapshot_epoch=getattr(provider_action, "snapshot_epoch", ""))
        target = referenced_target(action, self._snapshot)
        assert target is not None
        operation = {"Order": "order", "Create ticket": "ticket", "Delete": "delete"}.get(target.name)
        if operation is None:
            raise BridgeUnavailable("public mutation button semantics unsupported")
        parser = _PublicForms()
        parser.feed(self._snapshot.body)
        parser.close()
        matches = [fields for refs, fields in parser.forms if target.ref in refs]
        if len(matches) != 1:
            raise ValueError("unique original public form required")
        payload = dict(matches[0])
        if operation == "ticket" and (target.row_context, "Body") in self._fields:
            payload["body"] = self._fields[(target.row_context, "Body")]
        expected = {"order": {"quantity"}, "ticket": {"body"}, "delete": set()}[operation]
        if set(payload) != expected or any(not value for value in payload.values()):
            raise ValueError("original public form fields incomplete")
        version = self._snapshot.served_version
        if version is None:
            history = self._session.history(deadline_ns=self._deadline)
            if (not history.successful or not history.complete or not history.unfiltered
                    or history.cached or history.aliases
                    or (history.run_id, history.epoch, history.clock_id) != (
                        self._session.public.run_id, self._session.public.epoch, self._session.clock_id)
                    or type(history.served_version) is not int
                    or history.served_version != history.latest_version
                    or history.served_version < 0
                    or len(history.transitions) != history.served_version
                    or any(t.state_version != i for i, t in enumerate(history.transitions, 1))):
                raise BridgeUnavailable("current complete public version unavailable")
            version = history.served_version
        return Mutation(operation, target.row_context, tuple(sorted(payload.items())), version)


def create_offline_action_port(session: BrowserSession, row: dict, deadline_ns: int, *,
                               cleared_prompt_profiles: tuple[str, ...] = ()) -> "TrustedActionPortAdapter":
    """Fixed explicit D2 codec composition; no arbitrary loader or default launch.

    Missing accepted codec remains an unavailable source join. Prompt clearance
    precedes even a trusted clock read; the caller supplies public row selectors.
    """
    from .agents.prompts import select_prompt_profile
    schedule = row["schedule"]
    select_prompt_profile(arm=schedule["arm"], source_kind=schedule["source_kind"],
                          stage="mock" if schedule["source_kind"] == "mock" else "keyless",
                          cleared_prompt_profiles=cleared_prompt_profiles)
    from .agents import SessionLoopCodec
    if type(deadline_ns) is not int or session.now_ns() >= deadline_ns:
        raise BridgeUnavailable("offline composition deadline expired")
    resolver = OriginalPublicMutationResolver(session)
    codec = SessionLoopCodec(session.public,
                             (session.public.start_path, session.public.start_path + "/history"),
                             resolver, clock_id=session.clock_id)
    return TrustedActionPortAdapter(session, codec, arm=schedule["arm"],
                                    mutation_resolver=resolver)


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
    def __init__(self, session: BrowserSession, codec: LoopCodec | None, *, arm: Arm = "R0",
                 mutation_resolver: OriginalPublicMutationResolver | None = None):
        if codec is None:
            raise BridgeUnavailable("accepted D2 observation/action/feedback codec is not bound")
        self._session, self._codec, self._arm = session, codec, arm
        self.clock_id = session.clock_id
        self._started = session.context_receipt is not None
        self._halted = False
        self._resolver = mutation_resolver

    @property
    def codec_diagnostics(self) -> tuple:
        """Operator-only immutable producer diagnostics, including typed halts."""
        return tuple(getattr(self._codec, "diagnostics", ()))

    @property
    def observation_stamps(self) -> tuple:
        return tuple(getattr(self._codec, "observation_stamps", ()))

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
        if self._resolver is not None:
            self._resolver.observe(snapshot)
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
        if self._resolver is not None:
            self._resolver.begin(deadline_ns)
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
                if result.status == "acknowledged" and self._resolver is not None:
                    self._resolver.applied(mapped)
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
        if response_ns is None:
            self._halted = True
            # Accepted D2 feedback requires an actual authority timestamp. There
            # is no honest ActionFeedback object for an unbound completion.
            raise BridgeUnavailable("authoritative completion unavailable; no feedback timestamp invented")
        try:
            feedback = self._codec.feedback(request_id=request_id, clock_id=self.clock_id,
                                            response_ns=response_ns, result=result, error=error)
            if (getattr(feedback, "request_id", None) != request_id
                    or getattr(feedback, "run_id", None) != self._session.public.run_id
                    or getattr(feedback, "epoch", None) != self._session.public.epoch
                    or getattr(feedback, "clock_id", None) != self.clock_id
                    or getattr(feedback, "response_ns", None) != response_ns):
                raise ValueError("codec changed trusted feedback binding")
            acknowledged = (isinstance(result, InteractionReceipt) and result.status == "acknowledged"
                            or isinstance(result, ExecutionResult)
                            and result.disposition in {"acknowledged", "committed"})
            if getattr(feedback, "status", None) == "acknowledged" and not acknowledged:
                raise ValueError("codec acknowledged a failed/uncertain dispatch")
        except Exception as exc:
            self._halted = True
            raise BridgeUnavailable("accepted loop feedback codec unavailable") from exc
        if self.now_ns() >= deadline_ns:
            self._halted = True
            raise TimeoutError("loop action feedback deadline exceeded")
        return feedback
