"""Trusted visibility configuration; reconciliation budgets belong to policy."""
from dataclasses import dataclass


@dataclass(frozen=True)
class HistoryLag:
    delay_ns: int = 0

    def __post_init__(self) -> None:
        if type(self.delay_ns) is not int or self.delay_ns not in {0, 2_000_000_000}:
            raise ValueError("development history lag must be 0 or 2 seconds")

    def cutoff_ns(self, started_ns: int) -> int:
        return started_ns - self.delay_ns
