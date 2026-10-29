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
from .media_capture import MediaCapturePolicy, MediaCaptureSession
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
    def __init__(self, ipc: BrowserAuthorityIPC, *, record_interaction,
                 profile: str = "browser", media_policy: MediaCapturePolicy | None = None):
        if not callable(record_interaction):
            raise BridgeUnavailable("actual ordinary interaction recorder required")
        if profile not in {"browser", "browser_peer_in_process"}:
            raise BridgeUnavailable("closed browser composition profile required")
        self._record_interaction = record_interaction
        self._profile = profile
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
        if media_policy is not None and type(media_policy) is not MediaCapturePolicy:
            raise ValueError("explicit operator media policy required")
        self._media = MediaCaptureSession(media_policy or MediaCapturePolicy(),
                                          run_key=self.public.run_id)
        self._trace_attempted = False
        self._extra_videos = []
        self._resources_closed = False
        self._resource_close_error = None
        self.errors: list[tuple[str, str, str]] = []

    @property
    def media_manifest(self):
        """Private operator result; never included in DOM or action feedback."""
        return self._media.manifest

    @property
    def media_status(self) -> MediaStatus:
        return MediaStatus(*self._media.status)

    def finalize_media(self, *, outcome: str = "unknown", sample_key: str | None = None):
        """Operator outcome/paired sample key only, after resource close attempt."""
        if not self._resources_closed:
            raise ValueError("close browser resources before media selection")
        return self._media.finalize(outcome=outcome, sample_key=sample_key)

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
            if request.method == "POST":
                # The task's JSON receipt is delivered through authoritative
                # IPC. Keep the current native document/refs for R1 and later
                # public observation instead of navigating it to receipt JSON.
                # This transport response never determines action success.
                route.fulfill(status=204, headers={"cache-control": "no-store"}, body="")
            else:
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
            self._media.start()
            media_options = {}
            if self._media.active and self._media.video_dir is not None:
                media_options["record_video_dir"] = str(self._media.video_dir)
            try:
                self._context = self._browser.new_context(accept_downloads=False,
                    java_script_enabled=False, service_workers="block", **media_options)
            except Exception as exc:
                if not media_options:
                    raise
                self._media.note_error("video_context", exc)
                # No actor has run. A failed optional recording setup may leave
                # a context in this fresh private browser; close all known partial
                # contexts before a single nonrecording retry. Preserve all files.
                partial_contexts = tuple(self._browser.contexts)
                if len(partial_contexts) > 32:
                    raise BridgeUnavailable("partial context count unknown; no recording fallback")
                for partial in partial_contexts:
                    partial.close()  # a failed stop aborts rather than claiming freshness
                self._timeout(deadline_ns)
                self._context = self._browser.new_context(accept_downloads=False,
                    java_script_enabled=False, service_workers="block")
                media_options = {}
            if media_options:
                self._media.record_started("video")
            if self._media.active and self._media.trace_path is not None:
                # Mark before invocation: a partial start still needs stop/diagnostics.
                self._trace_attempted = True
                try:
                    self._context.tracing.start(screenshots=True, snapshots=True, sources=False)
                    self._media.record_started("trace")
                except Exception as exc:
                    self._media.note_error("trace_start", exc)
            self._policy = policy
            self._context.route("**/*", self._guard)
            # Block WebSockets before opening a page (requires preinstalled PW >=1.48).
            self._context.route_web_socket("**/*", lambda socket: socket.close())
            self._page = self._context.new_page()
            self._page.on("download", self._downloads)
            self._context.on("page", self._reject_extra_page)
            self._timeout(deadline_ns)
        except Exception as exc:
            self._media.note_error("context_start", exc)
            try:
                self.close_context()
            except Exception:
                # Preserve the original failed browser operation; cleanup retains
                # its own operator diagnostics, never a fabricated action result.
                pass
            raise
        return ContextReceipt(self.public.run_id, self.public.epoch, self.clock_id,
                              "playwright-" + uuid4().hex, True,
                              self.media_status,
                              profile=self._profile)

    def _reject_extra_page(self, page) -> None:
        if page is not self._page:
            self._route_error = "additional page refused"
            if self._media.active:
                # Video files remain private even if handle retrieval/inspection
                # fails. No directory scan or cleanup guesses their actual paths.
                self._media.note_error("video_extra_page_retained", RuntimeError())
                try:
                    video = page.video
                    if video is not None:
                        if len(self._extra_videos) >= 31:
                            raise ValueError("bounded extra-page video handles exceeded")
                        self._extra_videos.append(video)
                except Exception as exc:
                    self._media.note_error("video_handle", exc)
            page.close()

    def project_snapshot(self) -> Snapshot:
        """Actual DOM projection only: no IPC/clock reentry under peer state lock."""
        page = self._require_page()
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
        self._snapshot = value
        return value

    def snapshot(self, deadline_ns: int) -> Snapshot:
        self._timeout(deadline_ns)
        value = self.project_snapshot()
        self._timeout(deadline_ns)
        return value

    def prepare_action(self, request_id: str, deadline_ns: int) -> None:
        # Real browser preparation must enter through executor-owned accounting.
        raise BridgeUnavailable("counted browser preparation hook required")

    def prepare_counted_action(self, request_id: str, deadline_ns: int, operation) -> None:
        if self._prepared is not None:
            raise BridgeUnavailable("pending preparation must be consumed or cancelled")
        def prepare(end):
            self._prepared = request_id
            try:
                return self._ipc.prepare(request_id, end)
            except Exception:
                # Before returning, only this hook knows preparation may exist.
                # Once it returns the executor owns cleanup, including failures
                # in post-call accounting; do not cancel a second time here.
                self.cancel_action(request_id)
                raise
        prepared = operation("prepare", "prepared", prepare)
        observed = None
        if prepared.snapshot is not None:
            expected = prepared.snapshot
            self._policy.authorize(expected.url, "GET")
            if self._page.url != expected.url:
                raise BridgeUnavailable("prepare projection URL differs from current document")
            operation("prepare", "projection_installed", lambda end:
                self._page.set_content(expected.body, wait_until="domcontentloaded",
                                       timeout=self._timeout(end)))
            observed = operation("observe", "received", self.snapshot)
            if (observed.snapshot_epoch, observed.targets) != (expected.snapshot_epoch, expected.targets):
                raise BridgeUnavailable("installed public remap projection differs")
        # The peer independently calls project_snapshot under its lock. Count
        # before IPC; callback itself must not reenter clock/budget accounting.
        operation("observe" if observed is not None else "prepare", "installation_acknowledged",
            lambda end: self._ipc.call("installed", request_id, end,
                InstalledRender(prepared.installation_id, observed)))

    def prepare_submission(self, intent: Intent, request_id: str, deadline_ns: int, operation) -> None:
        """Reapply only original public values on the clicked ref's current form.

        No row/name semantics or private target lookup participates. Every actual
        fill is a separate local preparatory Step, never an ordinary peer event.
        """
        if self._prepared != request_id:
            raise BridgeUnavailable("bound counted preparation required")
        if not intent.payload:
            return
        button = operation("observe", "submission_button_observed",
                           lambda end: self._locator(intent.target.ref))
        form = button.locator("xpath=ancestor::form[1]")
        def unique(locator, message):
            if locator.count() != 1:
                raise ValueError(message)
            return locator
        operation("observe", "submission_form_observed",
                  lambda end: unique(form, "clicked reference requires one current form"))
        for name, value in intent.payload:
            if name not in {"body", "quantity"}:
                raise ValueError("closed admitted public payload field required")
            field = form.locator('[name="' + name + '"]')
            operation("observe", "submission_field_observed:" + name,
                      lambda end: unique(field, "unique current form field required"))
            if name == "quantity":
                actual = operation("observe", "public_payload_read:quantity",
                                   lambda end: field.input_value(timeout=self._timeout(end)))
                if actual != value:
                    raise BridgeUnavailable("readonly public quantity differs from admitted payload")
            else:
                operation("prepare", "public_payload_refilled:body",
                          lambda end: field.fill(value, timeout=self._timeout(end)))

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
        public = None
        try:
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
            self._timeout(deadline_ns)
            public = PublicInteraction(page.url, "acknowledged")
        except Exception as exc:
            # Actual command/postcheck failure remains an uncertain retained event.
            public = PublicInteraction(page.url, "unknown", type(exc).__name__)
        # Privileged actual-event producer runs before status retrieval. Its own
        # failure propagates; neither IPC nor the worker can fabricate this event.
        try:
            self._record_interaction(request_id, public)
            receipt = self._ipc.interaction(request_id, deadline_ns, public)
        except Exception:
            self._closed = True
            raise
        if public.status == "unknown":
            self._closed = True
        if action.kind in {"goto", "back", "reload"}:
            self._snapshot = None
        return receipt

    def close_context(self) -> None:
        if self._resources_closed:
            if self._resource_close_error is not None:
                raise BridgeUnavailable(self._resource_close_error)
            return
        self._resources_closed = True
        self._closed = True
        errors = []
        video = None
        if self._page is not None and self._media.active:
            try:
                video = self._page.video
            except Exception as exc:
                self._media.note_error("video_handle", exc)
        if self._context is not None and self._trace_attempted:
            try:
                self._context.tracing.stop(path=str(self._media.trace_path))
                self._media.register_completed("trace", self._media.trace_path)
            except Exception as exc:
                self._media.note_error("trace_stop", exc)
        context_closed = False
        for resource, method in ((self._context, "close"), (self._browser, "close"), (self._runtime, "stop")):
            if resource is not None:
                try:
                    getattr(resource, method)()
                    if resource is self._context:
                        context_closed = True
                        # Playwright completes videos when the context closes.
                        # Never ask for/claim a completed path before that point.
                        for completed_video in ([video] if video is not None else []) + self._extra_videos:
                            try:
                                self._media.register_completed("video", completed_video.path())
                            except Exception as exc:
                                self._media.note_error("video_path", exc)
                except Exception as exc:
                    errors.append(type(exc).__name__)
                    self._media.note_error("resource_close", exc)
        if self._media.active and not context_closed:
            self._media.note_error("video_close", RuntimeError("context close not completed"))
        if errors:
            self._resource_close_error = "browser cleanup incomplete: " + ",".join(errors)
            raise BridgeUnavailable(self._resource_close_error)
