"""Trusted executor ports; implementations must honor absolute deadlines."""
from dataclasses import dataclass
from typing import Literal, Protocol

from .contracts import HistoryRead, Intent, Origin, PublicTask
from .views import Page


class PreparedCancellationError(RuntimeError):
    """Trusted cleanup failed; the request remains pending until reconciled.

    Ports must propagate this separately from uncertain mutation outcomes.
    An executor must neither retry the mutation nor hide the pending request.
    """
    def __init__(self, request_id: str):
        self.request_id = request_id
        super().__init__("prepared cancellation failed for request " + request_id)


@dataclass(frozen=True)
class ActionReceipt:
    request_id: str
    run_id: str
    epoch: str
    clock_id: str
    response_ns: int
    status: Literal["acknowledged", "failed", "unchanged", "unknown"]
    error: str = ""


class BrowserPort(Protocol):
    """Trusted side only. No private answers/admin handles cross this seam.

    A real browser bridge must bind request identity and authority-clock response
    metadata out of band. Worker-controlled headers or client clocks cannot do so.
    cancel_action raises PreparedCancellationError on failed/unconfirmed cleanup;
    prepare_action and execute must preserve that exception when cleanup fails.
    Other execute returns/exceptions consume or successfully cancel preparation.
    """
    public: PublicTask
    clock_id: str

    def now_ns(self) -> int: ...
    def prepare_action(self, request_id: str, deadline_ns: int) -> None: ...
    def cancel_action(self, request_id: str) -> None: ...
    def observe(self, deadline_ns: int) -> Page: ...
    def execute(self, intent: Intent, request_id: str, origin: Origin,
                deadline_ns: int) -> ActionReceipt: ...
    def history(self, request_id: str, deadline_ns: int) -> HistoryRead: ...
    def wait(self, duration_ns: int, deadline_ns: int) -> None: ...
