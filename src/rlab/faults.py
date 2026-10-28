"""Operator-only deterministic development fault configuration.

Never serialize these settings to an actor observation. Each run selects one
semantic submission ordinal, shared across arms by the operator's frozen plan.
No hidden families, seed tables, timers or automatic retries live here.
"""
from dataclasses import dataclass
from typing import Literal

FaultKind = Literal["EXPIRED_VIEW", "STALE_ID", "INTERRUPTED_ACTION"]


@dataclass(frozen=True)
class FaultPlan:
    kind: FaultKind
    boundary: int = 1

    def __post_init__(self) -> None:
        if self.kind not in {"EXPIRED_VIEW", "STALE_ID", "INTERRUPTED_ACTION"}:
            raise ValueError("unsupported development fault")
        if type(self.boundary) is not int or self.boundary < 1:
            raise ValueError("boundary must be a positive submission ordinal")


EXPIRED_MESSAGE = "EXPIRED_VIEW: refresh before submission"
INTERRUPTED_MESSAGE = "INTERRUPTED_ACTION: confirmation unavailable"
