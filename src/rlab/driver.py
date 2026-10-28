"""Closed development adapter; future browser executor owns trusted lineage.

Not an HTTP server, isolation mechanism or live browser.
R0/R1 callers may use syntactically valid current refs without identity checks.
R3/R23 must invoke recovery.resolve before issuing a guarded mutation.
"""
from dataclasses import replace
import re
from typing import Callable

from .authority import Authority
from .contracts import HistoryRead, Intent, Origin, PublicTask
from .faults import EXPIRED_MESSAGE, INTERRUPTED_MESSAGE, FaultPlan
from .lag import HistoryLag
from .views import Page, render


def remap_page(page: Page) -> Page:
    """Reassign valid refs without adding the common executor identity guard.

    Keep the captured snapshot epoch valid: a stale ref now silently resolves
    to a different row. A later fresh observe gives R3 new refs for resolution.
    HTML and Target projections receive the same permutation.
    """
    refs = [target.ref for target in page.targets]
    if len(refs) < 2 or len(set(refs)) != len(refs):
        raise ValueError("STALE_ID requires at least two distinct visible refs")
    mapping = dict(zip(refs, refs[1:] + refs[:1]))

    def remap(match: re.Match[str]) -> str:
        return match[1] + mapping.get(match[2], match[2]) + '"'

    markup = re.sub(r'(\b(?:id|value)=")([^"]+)"', remap, page.html)
    targets = tuple(replace(target, ref=mapping[target.ref]) for target in page.targets)
    return replace(page, html=markup, targets=targets)


class DevelopmentTask:
    def __init__(self, authority: Authority, family: str, seed: int, *,
                 fault: FaultPlan | None = None, lag: HistoryLag | None = None,
                 acknowledge_remap: Callable[[Page], bool] | None = None):
        self.authority = authority  # trusted side only; never expose to worker
        self.family = family
        self.public: PublicTask = authority.setup(family, seed)
        self.page: Page | None = None
        self._acknowledge_remap = acknowledge_remap
        self._prepared_request: str | None = None
        self._prepared_kind: str | None = None
        self._preparation_failed = False
        if lag is not None:
            authority.configure_lag(self.public, lag)
        if fault is not None:
            authority.configure_fault(self.public, fault)

    def observe(self) -> Page:
        self.page = render(self.public, self.family,
                           self.authority.visible_items(self.public))
        return self.page

    def history(self, request_id: str) -> HistoryRead:
        """Ordinary public transition read; never bypass configured visibility."""
        return self.authority.history(self.public, request_id)

    def prepare_action(self, request_id: str) -> None:
        """Trusted executor hook, before R3's fresh observe/semantic guard.

        Reuse the same request ID in action. R0/R1 keep their captured page/ref;
        R3/R23 explicitly fresh-observe after this hook. Repeated preparation
        for the pending submission does not consume another semantic boundary.
        This is not mutation deduplication: every action still reaches authority.
        """
        if self._prepared_request == request_id:
            if self._preparation_failed:
                raise RuntimeError("fault preparation failed; seal as harness error")
            return
        if self._prepared_request is not None:
            raise ValueError("finish the prepared submission before another")
        if self.page is None:
            raise ValueError(EXPIRED_MESSAGE)
        kind = self.authority.prepare_boundary(self.public, request_id)
        self._prepared_request, self._prepared_kind = request_id, kind
        self._preparation_failed = True
        if kind == "STALE_ID":
            page = remap_page(self.page)
            # Local source adapter acknowledges its installed projection. A
            # browser transport must supply real render acknowledgement here.
            if self._acknowledge_remap is not None and not self._acknowledge_remap(page):
                raise RuntimeError("STALE_ID rerender was not acknowledged")
            self.page = page
            self.authority.fire_boundary(self.public, request_id, kind, page.snapshot_epoch)
        elif kind == "EXPIRED_VIEW":
            epoch = self.page.snapshot_epoch
            self.page = None
            self.authority.fire_boundary(self.public, request_id, kind, epoch)
        self._preparation_failed = False

    def cancel_action(self, request_id: str) -> None:
        """Release a successfully prepared submission when R3 refuses to issue."""
        if self._prepared_request != request_id or self._preparation_failed:
            raise ValueError("no successfully prepared submission to cancel")
        self.authority.cancel_boundary(self.public, request_id)
        self._prepared_request = self._prepared_kind = None

    def action(self, intent: Intent, ref: str, snapshot_epoch: str,
               request_id: str, origin: Origin) -> dict[str, object]:
        try:
            self.prepare_action(request_id)
            if (self._prepared_kind == "EXPIRED_VIEW" or self.page is None
                    or snapshot_epoch != self.page.snapshot_epoch):
                raise ValueError(EXPIRED_MESSAGE)
            matches = [t for t in self.page.targets if t.ref == ref]
            if len(matches) != 1:
                raise ValueError("missing reference")
            # Actual target derives from current DOM ref, not the actor's intended ID.
            # No common semantic identity guard: R0/R1 can hit a wrong row.
            issued = replace(intent, target_id=matches[0].row_context)
            result = self.authority.mutate(
                self.public, issued, request_id, origin,
                interrupted=self._prepared_kind == "INTERRUPTED_ACTION",
                snapshot_epoch=snapshot_epoch)
            if self._prepared_kind == "INTERRUPTED_ACTION":
                # The authority transaction has committed. Never recast this as
                # known pre-effect failure or hide a repeated mutation with dedup.
                raise TimeoutError(INTERRUPTED_MESSAGE)
            return result
        finally:
            self._prepared_request = self._prepared_kind = None
