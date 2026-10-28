"""Fixed lazy synchronous Playwright commands, operator side only.

Construction imports no Playwright and starts nothing. Later activation needs
preinstalled Playwright, a genuinely authenticated inherited receipt capability,
a bound server POST context, and separately qualified privileged isolation.
Browser routing alone is not OS egress/descendant enforcement.
"""
from uuid import uuid4

from .actions import Action, validate_action
from .browser import BridgeUnavailable, ContextReceipt, MediaStatus
from .browser_ipc import (BoundSubmission, BrowserAuthorityIPC, InstalledRender,
                          PublicInteraction)
from .contracts import Intent, Origin, Target
from .ports import PreparedCancellationError, UnboundActionResponse
from .routing import RoutePolicy
from .snapshot import Snapshot, referenced_target, validate_snapshot


# Fixed public DOM extraction only. No actor script, parameter or private state.
_PUBLIC_DOM = r"""() => {
 const forms = Array.from(document.querySelectorAll('form'));
 const epochs = [...new Set(forms.map(f => f.querySelector('input[name="snapshot"]')?.value).filter(Boolean))];
 const controls = Array.from(document.querySelectorAll('button[id],textarea[id],input[id]:not([type="hidden"]),select[id]'));
 const targets = controls.map(e => ({ref:e.id, role:e.tagName==='BUTTON'?'button':e.tagName==='SELECT'?'combobox':e.type==='number'?'spinbutton':'textbox',
 name:e.tagName==='BUTTON'?e.textContent.trim():(e.getAttribute('aria-label') || (e.closest('label') ? Array.from(e.closest('label').childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim() : '') || ''),
 row_context:e.closest('section')?.getAttribute('aria-label') || ''}));
 const copy = document.documentElement.cloneNode(true);
 const source = document.querySelectorAll('textarea,input,select');
 const dest = copy.querySelectorAll('textarea,input,select');
 source.forEach((e,i) => {if(e.tagName==='TEXTAREA') dest[i].textContent=e.value;
 else if(e.tagName==='INPUT') dest[i].setAttribute('value',e.value);
 else Array.from(dest[i].options).forEach(o=>o.selected=o.value===e.value);});
 return {epochs,targets,body:copy.outerHTML};
}"""


class PlaywrightBridge:
    def __init__(self, ipc: BrowserAuthorityIPC):
        self._ipc = ipc
        self.public, self.clock_id = ipc.public, ipc.clock_id
        self._policy = None
        self._runtime = self._browser = self._context = self._page = None
        self._snapshot = None
        self._prepared = None
        self._post_permit = False
        self._route_error = ""
        self._closed = False
        self._operation_deadline = None
        self.errors: list[tuple[str, str, str]] = []

    def now_ns(self) -> int:
        return self._ipc.now_ns()

    def _timeout(self, deadline_ns: int) -> int:
        remaining = deadline_ns - self.now_ns()
        if self._closed or remaining <= 0:
            raise TimeoutError("browser deadline/closed context")
        self._operation_deadline = deadline_ns
        return max(1, min(30000, (remaining + 999999) // 1000000))

    def _require_page(self):
        if self._page is None or self._policy is None:
            raise BridgeUnavailable("fresh browser context not open")
        return self._page

    def _guard(self, route) -> None:
        request = route.request
        try:
            self._policy.authorize(request.url, request.method,
                                   redirect=request.redirected_from is not None,
                                   upload=request.method == "POST" and not self._post_permit)
            if request.method == "POST":
                if not self._post_permit or request.resource_type != "document":
                    raise ValueError("only one bound ordinary form submission permitted")
                self._post_permit = False
                headers = request.headers
                content_type = headers.get("content-type", "")
                if not content_type.startswith("application/x-www-form-urlencoded"):
                    raise ValueError("upload/non-form body refused")
            if self._operation_deadline is None:
                raise ValueError("no bounded browser operation active")
            # Interception may not run again for redirects. Fetch exactly this
            # admitted URL without following any redirect, inspect the response,
            # and only then expose it to the browser.
            response = route.fetch(max_redirects=0,
                                   timeout=self._timeout(self._operation_deadline))
            if 300 <= response.status < 400:
                raise ValueError("redirect response refused")
            if "attachment" in response.headers.get("content-disposition", "").lower():
                raise ValueError("download response refused")
            self._timeout(self._operation_deadline)
            route.fulfill(response=response)
        except Exception as exc:
            self._route_error = type(exc).__name__
            route.abort("blockedbyclient")

    def _downloads(self, download) -> None:
        self._route_error = "download refused"
        download.cancel()

    def open_context(self, policy: RoutePolicy, deadline_ns: int) -> ContextReceipt:
        if self._runtime is not None or self._closed or policy.start_path != self.public.start_path:
            raise BridgeUnavailable("one new context per bridge required")
        timeout = self._timeout(deadline_ns)
        # Fixed lazy dependency, no plugin/module/command selectors.
        from playwright.sync_api import sync_playwright
        self._runtime = sync_playwright().start()
        try:
            self._browser = self._runtime.chromium.launch(headless=True, timeout=timeout)
            self._context = self._browser.new_context(accept_downloads=False,
                java_script_enabled=False, service_workers="block")
            self._policy = policy
            self._context.route("**/*", self._guard)
            # Block WebSockets before opening a page (requires preinstalled PW >=1.48).
            self._context.route_web_socket("**/*", lambda socket: socket.close())
            self._page = self._context.new_page()
            self._page.on("download", self._downloads)
            self._context.on("page", self._reject_extra_page)
            self._timeout(deadline_ns)
        except Exception:
            self.close_context()
            raise
        return ContextReceipt(self.public.run_id, self.public.epoch, self.clock_id,
                              "playwright-" + uuid4().hex, True,
                              MediaStatus(error="trace/video not requested; runtime unqualified"))

    def _reject_extra_page(self, page) -> None:
        if page is not self._page:
            self._route_error = "additional page refused"
            page.close()

    def snapshot(self, deadline_ns: int) -> Snapshot:
        page = self._require_page()
        self._timeout(deadline_ns)
        self._policy.authorize(page.url, "GET")
        data = page.evaluate(_PUBLIC_DOM)
        if (type(data) is not dict or set(data) != {"epochs", "targets", "body"}
                or type(data["epochs"]) is not list or len(data["epochs"]) > 1
                or type(data["targets"]) is not list or len(data["targets"]) > 64):
            raise ValueError("closed public DOM projection required")
        epoch = data["epochs"][0] if data["epochs"] else "public-history-" + uuid4().hex
        targets = tuple(Target(snapshot_epoch=epoch, **entry) for entry in data["targets"])
        value = validate_snapshot(Snapshot(self.public.run_id, self.public.epoch,
                    epoch, page.url, targets, data["body"]), self.public.run_id, self.public.epoch)
        if self._route_error:
            raise BridgeUnavailable("browser route/resource violation: " + self._route_error)
        self._timeout(deadline_ns)
        self._snapshot = value
        return value

    def prepare_action(self, request_id: str, deadline_ns: int) -> None:
        if self._prepared is not None:
            raise BridgeUnavailable("pending preparation must be consumed or cancelled")
        self._prepared = request_id
        try:
            prepared = self._ipc.prepare(request_id, deadline_ns)
            observed = None
            if prepared.snapshot is not None:
                expected = prepared.snapshot
                self._policy.authorize(expected.url, "GET")
                if self._page.url != expected.url:
                    raise BridgeUnavailable("prepare projection URL differs from current document")
                # Trusted public markup, scripts disabled, every resource routed.
                # set_content preserves the namespace URL and remapped IDs/epoch.
                self._page.set_content(expected.body, wait_until="domcontentloaded",
                                       timeout=self._timeout(deadline_ns))
                observed = self.snapshot(deadline_ns)
                if (observed.snapshot_epoch, observed.targets) != (expected.snapshot_epoch, expected.targets):
                    raise BridgeUnavailable("installed public remap projection differs")
            self._ipc.call("installed", request_id, deadline_ns,
                           InstalledRender(prepared.installation_id, observed))
        except Exception:
            self.cancel_action(request_id)
            raise

    def cancel_action(self, request_id: str) -> None:
        try:
            # Explicit bounded post-deadline cleanup in authority clock domain.
            self._ipc.call("cancel", request_id, self.now_ns() + 1_000_000_000)
        except Exception as exc:
            raise PreparedCancellationError(request_id) from exc
        self._prepared = None

    def _locator(self, ref: str):
        # Fixed attribute equality via locator filtering avoids actor CSS/JS.
        # refs are generated public identifiers; reject selector metacharacters.
        if not ref or any(not (c.isascii() and (c.isalnum() or c in "-_")) for c in ref):
            raise ValueError("canonical public reference required")
        locator = self._require_page().locator('[id="' + ref + '"]')
        if locator.count() != 1:
            raise ValueError("unique public control required")
        return locator

    def execute(self, intent: Intent, request_id: str, origin: Origin, deadline_ns: int):
        if self._prepared != request_id:
            raise BridgeUnavailable("bound preparation required")
        try:
            timeout = self._timeout(deadline_ns)
            if origin not in {"agent_direct", "controller_retry", "controller_resolve"}:
                raise ValueError("closed origin required")
            self._ipc.call("bind", request_id, deadline_ns,
                           BoundSubmission(intent, origin), root=intent.root_intent_id)
            # Bind may consume the earlier budget. Recheck before permitting a
            # POST and give click only the remaining absolute action budget.
            timeout = self._timeout(deadline_ns)
        except Exception:
            self.cancel_action(request_id)
            raise
        # After binding, a transport error is uncertain; never cancel/retry POST.
        self._post_permit = True
        try:
            try:
                self._locator(intent.target.ref).click(timeout=timeout, no_wait_after=True)
            except Exception as exc:
                # Preserve browser failure without inventing server completion.
                self.errors.append(("click", request_id, type(exc).__name__))
            return self._ipc.completion(intent, request_id, deadline_ns)
        except Exception as exc:
            raise UnboundActionResponse(request_id) from exc
        finally:
            self._post_permit = False
            self._prepared = None

    def history(self, request_id: str, deadline_ns: int):
        self._require_page()
        return self._ipc.history(request_id, deadline_ns)

    def wait(self, duration_ns: int, deadline_ns: int) -> None:
        if type(duration_ns) is not int or not 0 <= duration_ns <= 3_000_000_000:
            raise ValueError("bounded wait required")
        if self.now_ns() + duration_ns >= deadline_ns:
            raise TimeoutError("wait exceeds deadline")
        self._require_page().wait_for_timeout(duration_ns / 1_000_000)
        self._timeout(deadline_ns)

    def interact(self, action: Action, request_id: str, deadline_ns: int):
        validate_action(action)
        page = self._require_page()
        timeout = self._timeout(deadline_ns)
        if action.kind == "goto":
            page.goto(self._policy.authorize(action.path, "GET"),
                      wait_until="domcontentloaded", timeout=timeout)
        elif action.kind == "reload":
            self._policy.authorize(page.url, "GET")
            page.reload(wait_until="domcontentloaded", timeout=timeout)
        elif action.kind == "back":
            # Browser history could contain rejected navigation. Route guard
            # blocks it before any resource is sent; final URL is checked too.
            page.go_back(wait_until="domcontentloaded", timeout=timeout)
        elif action.kind in {"fill", "select"}:
            if self._snapshot is None:
                raise ValueError("captured control required")
            target = referenced_target(action, self._snapshot)
            locator = self._locator(target.ref)
            if action.kind == "fill":
                locator.fill(action.value, timeout=timeout)
            else:
                locator.select_option(value=action.value, timeout=timeout)
        elif action.kind == "wait":
            self.wait(action.duration_ms * 1_000_000, deadline_ns)
        elif action.kind != "finish":
            raise ValueError("mutation requires bound execute")
        self._policy.authorize(page.url, "GET")
        if self._route_error:
            raise BridgeUnavailable("browser request blocked: " + self._route_error)
        receipt = self._ipc.interaction(request_id, deadline_ns, PublicInteraction(page.url, "acknowledged"))
        if action.kind in {"goto", "back", "reload"}:
            self._snapshot = None
        return receipt

    def close_context(self) -> None:
        self._closed = True
        errors = []
        for resource, method in ((self._context, "close"), (self._browser, "close"), (self._runtime, "stop")):
            if resource is not None:
                try:
                    getattr(resource, method)()
                except Exception as exc:
                    errors.append(type(exc).__name__)
        if errors:
            raise BridgeUnavailable("browser cleanup incomplete: " + ",".join(errors))
