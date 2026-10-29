"""Trusted executor ports; implementations must honor absolute deadlines."""
from dataclasses import dataclass
from typing import Protocol

from .contracts import HistoryRead, Intent, Origin, PublicTask
from .views import Page


@dataclass(frozen=True)
class ActionReceipt:
    request_id: str
    run_id: str
    epoch: str
    clock_id: str
    response_ns: int
    status: str  # acknowledged | failed | unchanged | unknown
    error: str = ""


class BrowserPort(Protocol):
    """Trusted side only. No private answers/admin handles cross this seam.

    A real browser bridge must bind request identity and authority-clock response
    metadata out of band. Worker-controlled headers or client clocks cannot do so.
    """
    public: PublicTask
    clock_id: str

    def now_ns(self) -> int: ...
    def observe(self, deadline_ns: int) -> Page: ...
    def execute(self, intent: Intent, request_id: str, origin: Origin,
                deadline_ns: int) -> ActionReceipt: ...
    def history(self, request_id: str, deadline_ns: int) -> HistoryRead: ...
    def wait(self, duration_ns: int, deadline_ns: int) -> None: ...
