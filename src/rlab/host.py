"""Narrow WSGI source adapter plus in-process development BrowserPort.

No listener/launcher. A future trusted server supplies rlab.intent_context in
WSGI environ; HTTP headers/forms never supply original intent or effect lineage.
Unbound POST fails closed. No reset/seal/admin route exists.
"""
from dataclasses import asdict, dataclass
import json
import time
from urllib.parse import parse_qs

from .contracts import Intent, Origin
from .driver import DevelopmentTask
from .ports import ActionReceipt


class LocalTaskPort:
    """Trusted dev adapter, not a worker sandbox or an actual browser."""
    def __init__(self, task: DevelopmentTask):
        self.task = task
        self.public = task.public
        self.clock_id = task.authority.clock_id

    def now_ns(self) -> int:
        return time.monotonic_ns()

    def _check(self, deadline_ns: int) -> None:
        if self.now_ns() >= deadline_ns:
            raise TimeoutError("executor deadline")

    def observe(self, deadline_ns: int):
        self._check(deadline_ns)
        page = self.task.observe()
        self._check(deadline_ns)
        return page

    def execute(self, intent: Intent, request_id: str, origin: Origin,
                deadline_ns: int) -> ActionReceipt:
        self._check(deadline_ns)
        try:
            self.task.action(intent, intent.target.ref, intent.target.snapshot_epoch,
                             request_id, origin)
        except ValueError as exc:
            return ActionReceipt(request_id, self.public.run_id, self.public.epoch,
                                 self.clock_id, self.now_ns(), "failed", str(exc))
        # Deadline overrun may already have committed: never report no-effect.
        status = "unknown" if self.now_ns() >= deadline_ns else "acknowledged"
        return ActionReceipt(request_id, self.public.run_id, self.public.epoch,
                             self.clock_id, self.now_ns(), status)

    def history(self, request_id: str, deadline_ns: int):
        self._check(deadline_ns)
        read = self.task.authority.history(self.public, request_id)
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
    intent: Intent
    request_id: str
    origin: Origin
    deadline_ns: int


class TaskHost:
    """One task/epoch per application instance; mount only on approved loopback.

    Server/broker must inject a trusted per-request IntentContext after closed
    executor validation. WSGI environ keys cannot be set by incoming HTTP headers.
    This is an integration assumption, not demonstrated process authorization.
    """
    def __init__(self, port: LocalTaskPort, allowed_origin: str):
        from urllib.parse import urlsplit
        parsed = urlsplit(allowed_origin)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
                or parsed.path or parsed.query or parsed.fragment or parsed.username
                or parsed.password or parsed.port is None):
            raise ValueError("exact loopback HTTP origin with explicit port required")
        self.port = port
        self.origin = allowed_origin
        self.host = parsed.netloc

    def __call__(self, environ, start_response):
        def response(code, body, content_type="application/json; charset=utf-8"):
            data = body.encode("utf-8")
            start_response(code, [("Content-Type", content_type),
                                  ("Content-Length", str(len(data))),
                                  ("Cache-Control", "no-store"),
                                  ("X-Content-Type-Options", "nosniff"),
                                  ("Content-Security-Policy", "default-src 'none'; form-action 'self'")])
            return [data]

        path = environ.get("PATH_INFO", "")
        base = self.port.public.start_path
        method = environ.get("REQUEST_METHOD", "")
        if (environ.get("HTTP_HOST") != self.host
                or environ.get("wsgi.url_scheme") != "http"
                or environ.get("QUERY_STRING", "")):
            return response("403 Forbidden", '{"error":"origin or route rejected"}')
        if path not in {base, base + "/history", base + "/action"}:
            return response("404 Not Found", '{"error":"unknown route"}')
        try:
            if method == "GET" and path == base:
                page = self.port.observe(self.port.now_ns() + 3_000_000_000)
                return response("200 OK", page.html, "text/html; charset=utf-8")
            if method == "GET" and path == base + "/history":
                from uuid import uuid4
                read = self.port.history(uuid4().hex, self.port.now_ns() + 3_000_000_000)
                return response("200 OK", json.dumps(asdict(read)))
            if method != "POST" or path != base + "/action":
                return response("405 Method Not Allowed", '{"error":"method rejected"}')
            if environ.get("HTTP_ORIGIN") != self.origin:
                return response("403 Forbidden", '{"error":"POST origin rejected"}')
            context = environ.get("rlab.intent_context")
            if not isinstance(context, IntentContext):
                return response("503 Service Unavailable", '{"error":"trusted executor bridge required"}')
            if environ.get("CONTENT_TYPE", "").split(";", 1)[0] != "application/x-www-form-urlencoded":
                raise ValueError("form content type required")
            length = int(environ.get("CONTENT_LENGTH", "0"))
            if not 0 < length <= 8192:
                raise ValueError("bounded nonempty form required")
            raw = environ["wsgi.input"].read(length)
            if len(raw) != length:
                raise ValueError("truncated form")
            form = parse_qs(raw.decode("utf-8", errors="strict"),
                            keep_blank_values=True, strict_parsing=True, max_num_fields=8)
            if any(len(values) != 1 for values in form.values()):
                raise ValueError("duplicate form fields")
            submitted = {key: values[0] for key, values in form.items()}
            expected = dict(context.intent.payload)
            expected.update(ref=context.intent.target.ref,
                            snapshot=context.intent.target.snapshot_epoch)
            if submitted != expected:
                raise ValueError("form does not match admitted original action")
            receipt = self.port.execute(context.intent, context.request_id,
                                        context.origin, context.deadline_ns)
            code = "200 OK" if receipt.status == "acknowledged" else "409 Conflict"
            return response(code, json.dumps(asdict(receipt)))
        except (ValueError, UnicodeError, TimeoutError):
            return response("400 Bad Request", '{"error":"invalid form, run state or deadline"}')
