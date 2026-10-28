"""Closed development adapter; future browser executor owns trusted lineage.

Not an HTTP server, isolation mechanism, perturbation scheduler or live browser.
R0/R1 callers may use syntactically valid current refs without identity checks.
R3/R23 must invoke recovery.resolve before issuing a guarded mutation.
"""
from dataclasses import replace

from .authority import Authority
from .contracts import Intent, Origin, PublicTask
from .views import Page, render


class DevelopmentTask:
    def __init__(self, authority: Authority, family: str, seed: int):
        self.authority = authority  # trusted side only; never expose to worker
        self.family = family
        self.public: PublicTask = authority.setup(family, seed)
        self.page: Page | None = None

    def observe(self) -> Page:
        self.page = render(self.public, self.family,
                           self.authority.visible_items(self.public))
        return self.page

    def action(self, intent: Intent, ref: str, snapshot_epoch: str,
               request_id: str, origin: Origin) -> dict[str, object]:
        if self.page is None or snapshot_epoch != self.page.snapshot_epoch:
            raise ValueError("EXPIRED_VIEW: refresh before submission")
        matches = [t for t in self.page.targets if t.ref == ref]
        if len(matches) != 1:
            raise ValueError("missing reference")
        # Actual target derives from current DOM ref, not the actor's intended ID.
        # No common semantic identity guard: R0/R1 are allowed to hit a wrong row.
        issued = replace(intent, target_id=matches[0].row_context)
        return self.authority.mutate(self.public, issued, request_id, origin)
