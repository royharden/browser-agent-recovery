"""Privileged browser receipt server SOURCE; construction starts nothing.

Opaque capabilities/callbacks require authenticated operator provisioning. The
in-process exchange is convenience only. No listener, launcher, authority store,
authentication establishment or hard preemption is supplied here.
"""
from dataclasses import asdict
import json
import socket
import threading
import time
from typing import Callable
from uuid import uuid4

from .actions import Action, Mutation, text, validate_action
from .browser_ipc import (BoundSubmission, BrowserRequest, BrowserResponse,
                          InstalledRender, PreparedRender, PublicInteraction)
from .contracts import Intent, Target
from .driver import DevelopmentTask
from .host import IntentContext, LocalTaskPort, TaskHost
from .public_records import ActionReceipt, InteractionReceipt
from .snapshot import Snapshot, validate_snapshot


MAX_FRAME = 131072
OPERATIONS = frozenset({"clock", "prepare", "installed", "cancel", "bind",
                        "completed", "history", "interaction"})


def _closed(value: object, fields: set[str]) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise ValueError("closed browser record required")
    return value


def _target(raw: object) -> Target:
    return Target(**_closed(raw, {"ref", "snapshot_epoch", "role", "name", "row_context"}))


def _snapshot(raw: object) -> Snapshot | None:
    if raw is None:
        return None
    raw = _closed(raw, {"run_id", "epoch", "snapshot_epoch", "url", "targets",
                        "body", "served_version"})
    if type(raw["targets"]) is not list or len(raw["targets"]) > 64:
        raise ValueError("snapshot target cap")
    return Snapshot(**{**raw, "targets": tuple(_target(t) for t in raw["targets"])})


def _intent(raw: object) -> Intent:
    raw = _closed(raw, {"root_intent_id", "operation", "target_id", "payload",
                        "target", "before_version"})
    pairs = raw["payload"]
    if (type(pairs) is not list or len(pairs) > 8 or
            any(type(p) is not list or len(p) != 2 or
                any(type(v) is not str for v in p) for p in pairs)):
        raise ValueError("bounded public payload pairs required")
    return Intent(**{**raw, "target": _target(raw["target"]),
                     "payload": tuple(tuple(p) for p in pairs)})


def decode_request(frame: bytes) -> BrowserRequest:
    """Exact capped frame; JSON trailing bytes/duplicates/nonfinite refused."""
    if (type(frame) is not bytes or not 4 <= len(frame) <= MAX_FRAME + 4 or
            int.from_bytes(frame[:4], "big") != len(frame) - 4):
        raise ValueError("invalid request frame")

    def unique(pairs: list) -> dict:
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("duplicate JSON field")
        return result

    def nonfinite(_: str):
        raise ValueError("nonfinite JSON value")

    raw = _closed(json.loads(frame[4:].decode("utf-8"), object_pairs_hook=unique,
                             parse_constant=nonfinite, parse_float=nonfinite),
                  {"operation", "run_id", "epoch", "clock_id", "request_id",
                   "root_intent_id", "deadline_ns", "payload"})
    operation, body = raw["operation"], raw["payload"]
    if type(operation) is not str or operation not in OPERATIONS:
        raise ValueError("closed operation required")
    if operation == "bind":
        body = _closed(body, {"intent", "origin"})
        body = BoundSubmission(_intent(body["intent"]), body["origin"])
    elif operation == "installed":
        body = _closed(body, {"installation_id", "snapshot"})
        body = InstalledRender(body["installation_id"], _snapshot(body["snapshot"]))
    elif operation == "interaction":
        body = PublicInteraction(**_closed(body, {"url", "status", "error"}))
    elif body is not None:
        raise ValueError("unexpected operation payload")
    return BrowserRequest(**{**raw, "payload": body})


def encode_response(response: BrowserResponse) -> bytes:
    """Encode only the fixed response wrapper and known public payload DTOs."""
    from .contracts import HistoryRead
    if type(response) is not BrowserResponse or response.operation not in OPERATIONS:
        raise ValueError("known immutable response required")
    expected = {"prepare": PreparedRender, "completed": ActionReceipt,
                "interaction": InteractionReceipt, "history": HistoryRead}.get(
                    response.operation, type(None))
    if type(response.payload) is not expected:
        raise ValueError("operation-specific immutable response required")
    data = json.dumps(asdict(response), ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("ascii")
    if not 0 < len(data) <= MAX_FRAME:
        raise ValueError("response frame cap; truncation forbidden")
    return len(data).to_bytes(4, "big") + data


class BrowserReceiptPeer:
    """One operator task/context, serialized IPC, independently serviced HTTP.

    installed_snapshot must observe the actual privileged browser document;
    interaction_receipt must retrieve a retained actual trusted ordinary-action
    receipt. A callback's type or a caller's claimed metadata authenticates none
    of these facts. The embedding must provision and qualify those sources.
    """
    def __init__(self, task: DevelopmentTask, allowed_origin: str, *,
                 context_capability: object,
                 installed_snapshot: Callable[[], Snapshot | None],
                 interaction_receipt: Callable[[str], InteractionReceipt | None],
                 control_timeout_ns: int = 1_000_000_000,
                 max_requests: int = 4096):
        if (context_capability is None or not callable(installed_snapshot) or
                not callable(interaction_receipt) or type(control_timeout_ns) is not int or
                not 1 <= control_timeout_ns <= 3_000_000_000 or
                type(max_requests) is not int or not 1 <= max_requests <= 4096):
            raise ValueError("bounded operator composition required")
        self._port = LocalTaskPort(task)
        self.public, self.clock_id = task.public, task.authority.clock_id
        self._capability = context_capability
        self._installed_snapshot, self._interaction_receipt = installed_snapshot, interaction_receipt
        self._control_ns, self._max_requests = control_timeout_ns, max_requests
        self._ipc_owner = threading.Lock()
        self._condition = threading.Condition(threading.RLock())
        self._host = TaskHost(self._port, allowed_origin, receipt_sink=self._retain_terminal)
        self._seen: dict[str, str] = {}
        self._roots: dict[str, tuple] = {}
        self._prepared: str | None = None
        self._installation: PreparedRender | None = None
        self._installed = False
        self._binding: IntentContext | None = None
        self._dispatching = False
        self._consumed = False
        self._terminals: dict[str, ActionReceipt] = {}
        self._delivered: set[str] = set()
        self._interactions: dict[str, InteractionReceipt] = {}
        self._attempts: dict[str, str] = {}
        self._halted = False
        self._last_ns = -1

    def _now(self) -> int:
        stamp = self._port.now_ns()
        if type(stamp) is not int or stamp < 0 or stamp < self._last_ns:
            self._halted = True
            raise ValueError("authority clock unavailable/regressed")
        self._last_ns = stamp
        return stamp

    def _deadline(self, deadline: int) -> int:
        if type(deadline) is not int or deadline < 0:
            raise ValueError("absolute authority deadline required")
        remaining = deadline - self._now()
        if remaining <= 0:
            raise TimeoutError("authority deadline exhausted")
        return remaining

    def _fresh(self, request_id: str, kind: str) -> None:
        reserved = request_id in self._interactions
        if (request_id == "authority-clock" or request_id in self._seen or
                (reserved and kind != "interaction") or
                (not reserved and len(self._seen.keys() | self._interactions.keys()) >= self._max_requests)):
            raise ValueError("request reuse or retained ledger cap")
        self._seen[request_id] = kind

    def _validate(self, request: BrowserRequest) -> None:
        if (type(request) is not BrowserRequest or type(request.operation) is not str or
                request.operation not in OPERATIONS or
                (request.run_id, request.epoch, request.clock_id) !=
                (self.public.run_id, self.public.epoch, self.clock_id)):
            raise ValueError("unbound browser request")
        text(request.request_id, "request", 160)
        text(request.root_intent_id, "root", 160, empty=True)
        if type(request.deadline_ns) is not int or request.deadline_ns < 0:
            raise ValueError("absolute authority deadline required")
        if request.operation == "clock":
            if (request.request_id != "authority-clock" or request.deadline_ns != 0 or
                    request.root_intent_id or request.payload is not None):
                raise ValueError("fixed bounded clock control request required")
        elif request.operation not in {"cancel", "completed"}:
            self._deadline(request.deadline_ns)
        if request.operation not in {"bind", "completed"} and request.root_intent_id:
            raise ValueError("unexpected root lineage")
        expected = {"bind": BoundSubmission, "installed": InstalledRender,
                    "interaction": PublicInteraction}.get(request.operation, type(None))
        if type(request.payload) is not expected:
            raise ValueError("closed operation payload required")

    def exchange(self, request: BrowserRequest) -> BrowserResponse:
        # Nonblocking ownership prevents concurrent IPC lifecycle callers. HTTP
        # never takes this lock, and Condition.wait releases the state lock.
        if not self._ipc_owner.acquire(blocking=False):
            raise RuntimeError("serialized peer exchange required")
        try:
            with self._condition:
                self._validate(request)
                if self._halted and request.operation not in {"clock", "completed"}:
                    raise RuntimeError("peer halted; retained reconciliation required")
                value = self._operate(request)
                stamp = self._now()
                if request.operation not in {"clock", "cancel", "completed"}:
                    self._deadline(request.deadline_ns)
                return BrowserResponse(request.operation, request.run_id, request.epoch,
                                       request.clock_id, request.request_id,
                                       request.root_intent_id, stamp, value)
        finally:
            self._ipc_owner.release()

    def _operate(self, request: BrowserRequest):
        op, rid = request.operation, request.request_id
        if op == "clock":
            return None
        if op == "prepare":
            if self._prepared is not None or self._binding is not None or self._dispatching:
                raise ValueError("pending action must terminate before preparation")
            self._fresh(rid, "action")
            self._prepared = rid  # Retain before task call: failed cleanup is uncertain.
            before = self._port.task.page
            self._port.prepare_action(rid, request.deadline_ns)
            page = self._port.task.page
            projection = None
            if page is not None and page is not before:
                # Match fixed public DOM order: each row's ordinary controls
                # precede its mutation button. Do not omit F2 textareas.
                targets = tuple(t for button in page.targets
                                for t in (*tuple(c for c in page.controls
                                                 if c.row_context == button.row_context), button))
                projection = validate_snapshot(Snapshot(self.public.run_id, self.public.epoch,
                    page.snapshot_epoch, self._host.origin + self.public.start_path,
                    targets, page.html), self.public.run_id, self.public.epoch)
            self._installation = PreparedRender(uuid4().hex, projection)
            self._installed = False
            return self._installation
        if op == "installed":
            if (rid != self._prepared or self._installed or self._installation is None or
                    request.payload.installation_id != self._installation.installation_id):
                raise ValueError("one exact prepared installation required")
            expected = self._installation.snapshot
            supplied = request.payload.snapshot
            if expected is None:
                if supplied is not None:
                    raise ValueError("unexpected installation projection")
            else:
                actual = self._installed_snapshot()
                for projection in (supplied, actual):
                    validate_snapshot(projection, self.public.run_id, self.public.epoch)
                    if (projection.url, projection.snapshot_epoch, projection.targets) != (
                            expected.url, expected.snapshot_epoch, expected.targets):
                        raise ValueError("actual installed projection identity differs")
            self._installed = True
            return None
        if op == "cancel":
            if rid != self._prepared or self._dispatching or self._consumed:
                raise ValueError("prepared unissued request required for cancellation")
            try:
                self._port.cancel_action(rid)
            except BaseException:
                self._halted = True
                self._attempts[rid] = "cleanup_unknown"
                raise
            self._binding = None
            self._prepared = self._installation = None
            self._installed = False
            self._attempts[rid] = "cancelled"
            return None
        if op == "bind":
            if (rid != self._prepared or not self._installed or self._binding is not None or
                    self._consumed or self._dispatching):
                raise ValueError("one installed unissued action required")
            value = request.payload
            intent = value.intent
            if type(intent) is not Intent or type(intent.target) is not Target:
                raise ValueError("known immutable original intent required")
            text(intent.root_intent_id, "root", 160)
            for field, cap in (("ref", 160), ("snapshot_epoch", 160), ("role", 64),
                               ("name", 256), ("row_context", 512)):
                text(getattr(intent.target, field), "target " + field, cap,
                     empty=field in {"name", "row_context"})
            if (request.root_intent_id != intent.root_intent_id or value.origin not in {
                    "agent_direct", "controller_retry", "controller_resolve"}):
                raise ValueError("trusted original lineage required")
            # Validate public syntax without imposing a common semantic row/name
            # guard. DevelopmentTask.action derives the actual target from ref.
            mutation = Mutation(intent.operation, intent.target_id, intent.payload, intent.before_version)
            validate_action(Action("click", intent.target.ref, intent.target.snapshot_epoch,
                                   intent=mutation))
            signature = (intent.operation, intent.target_id, intent.payload, intent.before_version)
            if self._roots.setdefault(intent.root_intent_id, signature) != signature:
                raise ValueError("original root intent changed")
            self._binding = IntentContext(intent, rid, value.origin, request.deadline_ns)
            self._attempts[rid] = "bound_unissued"
            return None
        if op == "completed":
            context = self._binding
            if (context is None or rid != context.request_id or
                    request.root_intent_id != context.intent.root_intent_id or
                    request.deadline_ns != context.deadline_ns):
                raise ValueError("exact retained binding required")
            # A separate monotonic control cap bounds waiting even if the
            # authority clock stalls. Neither clock creates a fake completion.
            control_end = time.monotonic_ns() + self._control_ns
            while rid not in self._terminals:
                remaining = min(request.deadline_ns - self._now(),
                                control_end - time.monotonic_ns())
                if remaining <= 0:
                    self._halted = True
                    self._attempts[rid] = "completion_unknown"
                    raise TimeoutError("actual server terminal receipt unavailable; halt")
                self._condition.wait(remaining / 1_000_000_000)
            receipt = self._terminals[rid]
            if rid in self._delivered:
                raise ValueError("completion already delivered")
            self._delivered.add(rid)
            if self._dispatching:
                # Receipt is retained before response delivery; dispatch may
                # still be unwinding. Do not release its binding prematurely.
                return receipt
            self._release_action()
            return receipt
        if op == "history":
            if self._dispatching:
                raise ValueError("HTTP task operation in progress")
            self._fresh(rid, "history")
            return self._port.history(rid, request.deadline_ns)
        if op == "interaction":
            if self._prepared is not None or self._dispatching:
                raise ValueError("action lifecycle still pending")
            self._fresh(rid, "interaction")
            public = request.payload
            text(public.url, "interaction URL", 768)
            text(public.error, "interaction error", 4096, empty=True)
            if public.status not in {"acknowledged", "unknown"}:
                raise ValueError("closed interaction status")
            receipt = self._interactions.get(rid)
            if receipt is None:
                receipt = self._interaction_receipt(rid)
            now = self._now()
            if (type(receipt) is not InteractionReceipt or
                    (receipt.request_id, receipt.run_id, receipt.epoch, receipt.clock_id,
                     receipt.url, receipt.status) != (rid, self.public.run_id, self.public.epoch,
                         self.clock_id, public.url, public.status) or
                    type(receipt.response_ns) is not int or not 0 <= receipt.response_ns <= now or
                    receipt.response_ns >= request.deadline_ns):
                self._attempts[rid] = "interaction_unbound"
                self._halted = True
                raise ValueError("actual retained ordinary interaction receipt unavailable")
            self._interactions[rid] = receipt
            return receipt
        raise ValueError("unsupported operation")

    def _release_action(self) -> None:
        self._binding = None
        self._prepared = self._installation = None
        self._installed = self._consumed = False

    def record_interaction(self, context_capability: object, request_id: str,
                           public: PublicInteraction) -> InteractionReceipt:
        """Trusted ordinary-action completion hook, BEFORE IPC interaction.

        Only the authenticated privileged dispatcher that actually observed the
        accepted action may call this. PublicInteraction arriving on IPC alone
        never calls this hook and cannot manufacture acceptance/timing.
        """
        with self._condition:
            if context_capability is not self._capability:
                raise PermissionError("operator context capability required")
            text(request_id, "interaction request", 160)
            if (self._halted or self._prepared is not None or self._dispatching or
                    type(public) is not PublicInteraction or request_id == "authority-clock" or
                    request_id in self._seen or
                    request_id in self._interactions or
                    len(self._seen.keys() | self._interactions.keys()) >= self._max_requests):
                raise ValueError("fresh bounded actual ordinary action required")
            text(public.url, "interaction URL", 768)
            text(public.error, "interaction error", 4096, empty=True)
            if public.status not in {"acknowledged", "unknown"}:
                raise ValueError("closed ordinary action status")
            receipt = InteractionReceipt(request_id, self.public.run_id, self.public.epoch,
                self.clock_id, self._now(), public.status, public.url, public.error)
            self._interactions[request_id] = receipt
            return receipt

    def _retain_terminal(self, receipt: ActionReceipt) -> None:
        with self._condition:
            context = self._binding
            if (type(receipt) is not ActionReceipt or context is None or
                    not self._dispatching or not self._consumed or
                    (receipt.request_id, receipt.run_id, receipt.epoch, receipt.clock_id) !=
                    (context.request_id, self.public.run_id, self.public.epoch, self.clock_id) or
                    receipt.request_id in self._terminals or type(receipt.response_ns) is not int or
                    not 0 <= receipt.response_ns <= self._now() or receipt.status not in {
                        "acknowledged", "failed", "unchanged", "unknown"}):
                self._halted = True
                raise ValueError("invalid or duplicate actual terminal receipt")
            self._terminals[receipt.request_id] = receipt
            self._attempts[receipt.request_id] = "server_terminal"
            self._condition.notify_all()

    def dispatch_http(self, context_capability: object, environ, start_response):
        """Called ONLY by the operator's authenticated per-context dispatcher.

        The capability argument is not extracted from any HTTP field. Ambient
        environ context is discarded. No reset/seal/admin route is introduced.
        """
        with self._condition:
            if context_capability is not self._capability:
                raise PermissionError("operator context capability required")
            if self._halted or self._dispatching:
                raise RuntimeError("peer halted or concurrent HTTP dispatch")
            clean = dict(environ)
            clean.pop("rlab.intent_context", None)
            is_post = clean.get("REQUEST_METHOD") == "POST"
            context = self._binding if is_post else None
            if is_post:
                if context is None or self._consumed:
                    raise ValueError("one next bound POST required")
                self._deadline(context.deadline_ns)
                self._consumed = True  # Consume before body read or task effect.
                self._attempts[context.request_id] = "dispatch_started"
                clean["rlab.intent_context"] = context
            elif self._prepared is not None:
                # A GET render would replace the prepared remap before POST.
                raise ValueError("HTTP render forbidden during prepared action")
            self._dispatching = True
        try:
            return self._host(clean, start_response)
        finally:
            with self._condition:
                self._dispatching = False
                if context is not None and context.request_id not in self._terminals:
                    # Includes validation/timeout/exception before a terminal
                    # sink receipt. Do not infer no effect or retry the POST.
                    self._attempts[context.request_id] = "dispatch_without_terminal_unknown"
                    self._halted = True
                elif context is not None and context.request_id in self._delivered:
                    self._release_action()
                self._condition.notify_all()

    def exchange_frame(self, frame: bytes, deadline_ns: int) -> bytes:
        request = decode_request(frame)
        if type(deadline_ns) is not int or request.deadline_ns != deadline_ns:
            raise ValueError("outer frame deadline mismatch")
        return encode_response(self.exchange(request))

    def serve_once(self, connection: socket.socket, *, context_capability: object) -> None:
        """One frame on a preconnected operator-authenticated AF_UNIX socket.

        No connection establishment or credential claim. Operator must verify
        peer credentials/context and exclusive ownership before supplying this
        capability. Socket timeouts bound IO, not arbitrary task/callback work.
        """
        if (context_capability is not self._capability or
                type(connection) is not socket.socket or connection.family != socket.AF_UNIX):
            raise PermissionError("preprovisioned AF_UNIX context capability required")
        end = time.monotonic_ns() + self._control_ns
        previous = connection.gettimeout()

        def receive(count: int) -> bytes:
            parts = bytearray()
            while len(parts) < count:
                remaining = end - time.monotonic_ns()
                if remaining <= 0:
                    raise TimeoutError("bounded frame read exhausted")
                connection.settimeout(remaining / 1_000_000_000)
                chunk = connection.recv(count - len(parts))
                if not chunk:
                    raise EOFError("truncated browser frame")
                parts.extend(chunk)
            return bytes(parts)

        try:
            header = receive(4)
            length = int.from_bytes(header, "big")
            if not 0 < length <= MAX_FRAME:
                raise ValueError("frame cap before payload allocation/read")
            request = decode_request(header + receive(length))
            response = encode_response(self.exchange(request))
            remaining = self._control_ns
            if request.operation not in {"clock", "cancel", "completed"}:
                with self._condition:
                    remaining = min(remaining, request.deadline_ns - self._now())
            if remaining <= 0:
                raise TimeoutError("response IO deadline exhausted; retained result remains")
            connection.settimeout(remaining / 1_000_000_000)
            connection.sendall(response)
        finally:
            connection.settimeout(previous)
