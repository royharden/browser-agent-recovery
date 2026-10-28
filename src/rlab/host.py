"""Provisional WSGI adapter and trusted in-process development BrowserPort.

No listener/launcher. A future trusted bridge injects rlab.intent_context; HTTP
headers/forms cannot supply intent or lineage. Unbound POST fails closed.
"""
from dataclasses import asdict, dataclass
import json
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from .contracts import HistoryRead, Intent, Origin
from .driver import DevelopmentTask
from .ports import ActionReceipt
from .views import Page


class LocalTaskPort:
    """Trusted dev adapter, not a browser, worker API or isolation mechanism."""

    def __init__(self, task: DevelopmentTask):
        self.task = task
        self.public = task.public
        self.clock_id = task.authority.clock_id

    def now_ns(self) -> int:
        return self.task.authority.now_ns()

    def _check(self, deadline_ns: int) -> None:
        if self.now_ns() >= deadline_ns:
            raise TimeoutError("executor deadline")

    def observe(self, deadline_ns: int) -> Page:
        self._check(deadline_ns)
        page = self.task.observe()
        self._check(deadline_ns)
        return page

    def prepare_action(self, request_id: str, deadline_ns: int) -> None:
        """Stage one action boundary before guarded observation/resolution.

        The executor must reuse this request ID for execute; task.action handles
        preparation itself for arms that do not request an R3 guard.
        """
        self._check(deadline_ns)
        if not request_id:
            raise ValueError("trusted request identity required")
        self.task.prepare_action(request_id)
        self._check(deadline_ns)

    def execute(self, intent: Intent, request_id: str, origin: Origin,
                deadline_ns: int) -> ActionReceipt:
        self._check(deadline_ns)
        if not request_id or origin not in {
                "agent_direct", "controller_retry", "controller_resolve"}:
            raise ValueError("trusted request lineage required")
        try:
            result = self.task.action(
                intent, intent.target.ref, intent.target.snapshot_epoch,
                request_id, origin)
        except ValueError as exc:
            # Confirmed task seam: ValueError is a pre-effect rejection only.
            return ActionReceipt(request_id, self.public.run_id, self.public.epoch,
                                 self.clock_id, self.now_ns(), "failed", str(exc))
        except Exception as exc:
            # Other task exceptions may follow a committed effect. In particular,
            # interrupted-action TimeoutError is never evidence of absence.
            return ActionReceipt(request_id, self.public.run_id, self.public.epoch,
                                 self.clock_id, self.now_ns(), "unknown", str(exc))
        response_ns = self.now_ns()
        status = "acknowledged"
        error = ""
        if isinstance(result, dict):
            reported = result.get("status", "acknowledged")
            status = reported if isinstance(reported, str) and reported in {
                "acknowledged", "failed", "unchanged", "unknown"} else "unknown"
            error = str(result.get("error", ""))
        if response_ns >= deadline_ns:
            status = "unknown"
            error = "action exceeded deadline; effect may have committed"
        return ActionReceipt(request_id, self.public.run_id, self.public.epoch,
                             self.clock_id, response_ns, status, error)

    def history(self, request_id: str, deadline_ns: int) -> HistoryRead:
        self._check(deadline_ns)
        # DL2's task seam owns fault/lag visibility. Never bypass it through the
        # authority object: that would reveal immediate history under lag.
        read = self.task.history(request_id)
        self._check(deadline_ns)
        return read

    def wait(self, duration_ns: int, deadline_ns: int) -> None:
        self._check(deadline_ns)
        if duration_ns < 0 or self.now_ns() + duration_ns >= deadline_ns:
            raise TimeoutError("wait would exceed executor deadline")
        time.sleep(duration_ns / 1_000_000_000)
        self._check(deadline_ns)


@dataclass(frozen=True)
class IntentContext:
    """Trusted bridge context, never constructed from a worker form/header."""

    intent: Intent
    request_id: str
    origin: Origin
    deadline_ns: int


class TaskHost:
    """One task/epoch per instance, with exact loopback routes and origin.

    The trusted server must bind each POST to its admitted executor operation
    out of band, apply body/read timeouts and prevent actor access to environ.
    This source does not establish those process/security properties.
    """

    def __init__(self, port: LocalTaskPort, allowed_origin: str):
        parsed = urlsplit(allowed_origin)
        if (parsed.scheme != "http"
                or parsed.hostname not in {"127.0.0.1", "localhost"}
                or parsed.path or parsed.query or parsed.fragment
                or parsed.username or parsed.password or parsed.port is None):
            raise ValueError("exact loopback HTTP origin with explicit port required")
        base = port.public.start_path
        if (not base.startswith("/tasks/") or "//" in base
                or any(part in {"", ".", ".."} for part in base[1:].split("/"))
                or any(char in base for char in "?#%\\")):
            raise ValueError("canonical local task path required")
        self.port = port
        self.origin = allowed_origin
        self.host = parsed.netloc
        self.base = base

    def __call__(self, environ, start_response):
        def response(code, body, content_type="application/json; charset=utf-8"):
            data = body.encode("utf-8")
            start_response(code, [("Content-Type", content_type),
                                  ("Content-Length", str(len(data))),
                                  ("Cache-Control", "no-store"),
                                  ("X-Content-Type-Options", "nosniff"),
                                  ("Content-Security-Policy",
                                   "default-src 'none'; form-action 'self'; frame-ancestors 'none'")])
            return [data]

        path = environ.get("PATH_INFO", "")
        method = environ.get("REQUEST_METHOD", "")
        if (environ.get("HTTP_HOST") != self.host
                or environ.get("wsgi.url_scheme") != "http"
                or environ.get("QUERY_STRING", "")):
            return response("403 Forbidden", '{"error":"origin or route rejected"}')
        if path not in {self.base, self.base + "/history", self.base + "/action"}:
            return response("404 Not Found", '{"error":"unknown route"}')
        try:
            if method == "GET" and path == self.base:
                page = self.port.observe(self.port.now_ns() + 3_000_000_000)
                return response("200 OK", page.html, "text/html; charset=utf-8")
            if method == "GET" and path == self.base + "/history":
                read = self.port.history(uuid4().hex, self.port.now_ns() + 3_000_000_000)
                return response("200 OK", json.dumps(asdict(read)))
            if method != "POST" or path != self.base + "/action":
                return response("405 Method Not Allowed", '{"error":"method rejected"}')
            if environ.get("HTTP_ORIGIN") != self.origin:
                return response("403 Forbidden", '{"error":"POST origin rejected"}')
            context = environ.get("rlab.intent_context")
            if not isinstance(context, IntentContext):
                return response("503 Service Unavailable",
                                '{"error":"trusted executor bridge required"}')
            if (not context.request_id or context.origin not in {
                    "agent_direct", "controller_retry", "controller_resolve"}):
                raise ValueError("invalid trusted context")
            deadline_ns = min(context.deadline_ns,
                              self.port.now_ns() + 3_000_000_000)
            self.port._check(deadline_ns)
            if environ.get("CONTENT_TYPE", "").split(";", 1)[0] != "application/x-www-form-urlencoded":
                raise ValueError("form content type required")
            length = int(environ.get("CONTENT_LENGTH", "0"))
            if not 0 < length <= 8192:
                raise ValueError("bounded nonempty form required")
            raw = environ["wsgi.input"].read(length)
            self.port._check(deadline_ns)
            if len(raw) != length:
                raise ValueError("truncated form")
            form = parse_qs(raw.decode("utf-8", errors="strict"),
                            keep_blank_values=True, strict_parsing=True,
                            errors="strict", max_num_fields=8)
            if any(len(values) != 1 for values in form.values()):
                raise ValueError("duplicate form fields")
            submitted = {key: values[0] for key, values in form.items()}
            expected = dict(context.intent.payload)
            if (len(expected) != len(context.intent.payload)
                    or {"ref", "snapshot"} & expected.keys()):
                raise ValueError("invalid admitted form fields")
            expected.update(ref=context.intent.target.ref,
                            snapshot=context.intent.target.snapshot_epoch)
            if submitted != expected:
                raise ValueError("form does not match admitted original action")
            receipt = self.port.execute(context.intent, context.request_id,
                                        context.origin, deadline_ns)
            code = "200 OK" if receipt.status == "acknowledged" else "409 Conflict"
            return response(code, json.dumps(asdict(receipt)))
        except (ValueError, UnicodeError, TimeoutError):
            return response("400 Bad Request",
                            '{"error":"invalid form, run state or deadline"}')
