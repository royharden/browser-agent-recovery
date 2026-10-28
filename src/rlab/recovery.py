"""Bounded R2/R3/R23 decisions on visible evidence only.

The driver owns action execution, timing and accounting. This module neither
reads authority state nor sleeps, polls, retries HTTP or calls a model.
"""
from dataclasses import dataclass, field
from typing import Literal

from .contracts import FailedAction, HistoryRead, Intent, Target

Verdict = Literal["present", "absent", "ambiguous"]


def verify(intent: Intent, failed: FailedAction, read: HistoryRead,
           seen_requests: set[str]) -> Verdict:
    fresh = (
        read.run_id == failed.run_id and read.epoch == failed.epoch
        and read.clock_id == failed.clock_id
        and bool(read.request_id) and read.request_id not in seen_requests
        and read.started_ns > failed.response_ns
        and read.completed_ns >= read.started_ns
        and read.successful and read.complete and read.unfiltered
        and not read.cached and not read.aliases
    )
    n, m = read.served_version, read.latest_version
    if (not fresh or n is None or m is None or n != m
            or n < intent.before_version or intent.before_version < 0):
        return "ambiguous"
    versions = [t.state_version for t in read.transitions]
    # A complete history includes each transition, including deletion history.
    if len(versions) != n or any(v != i for i, v in enumerate(versions, start=1)):
        return "ambiguous"
    matches = [t for t in read.transitions
               if t.state_version > intent.before_version
               and t.operation == intent.operation
               and t.target_id == intent.target_id and t.payload == intent.payload]
    if len(matches) == 1:
        return "present"
    return "ambiguous" if matches else "absent"


def resolve(intent: Intent, fresh_targets: tuple[Target, ...],
            snapshot_epoch: str) -> Target | None:
    """R3 semantic identity, never a TaskSpec lookup or stale-ref fallback."""
    if not snapshot_epoch or snapshot_epoch == intent.target.snapshot_epoch:
        return None
    matches = [t for t in fresh_targets
               if t.snapshot_epoch == snapshot_epoch
               and (t.role, t.name, t.row_context) == (
                   intent.target.role, intent.target.name, intent.target.row_context)]
    return matches[0] if len(matches) == 1 else None


@dataclass
class Reconciliation:
    """One failed root intent: at most one retry, with a fixed total budget.

    Every inspect call consumes a probe step, including inconclusive reads.
    A caller must retain this object across the retry and its failed response;
    constructing a fresh object would incorrectly reset the retry cap.
    """
    intent: Intent
    failed: FailedAction
    budget_ns: int = 4_000_000_000
    max_probes: int = 8
    probes: int = field(default=0, init=False)
    retry_used: bool = field(default=False, init=False)
    terminal: bool = field(default=False, init=False)
    seen_requests: set[str] = field(default_factory=set, init=False)
    awaiting_retry_response: bool = field(default=False, init=False)
    _deadline_ns: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._deadline_ns = self.failed.response_ns + self.budget_ns

    def retry_failed(self, failed: FailedAction) -> None:
        """Advance freshness after the retry, without extending the deadline."""
        if (not self.awaiting_retry_response
                or (failed.run_id, failed.epoch, failed.clock_id) != (
                    self.failed.run_id, self.failed.epoch, self.failed.clock_id)
                or failed.response_ns < self.failed.response_ns):
            self.terminal = True
            raise ValueError("invalid retry response identity/timing")
        self.failed = failed
        self.awaiting_retry_response = False

    def inspect(self, read: HistoryRead, now_ns: int) -> str:
        if self.terminal or self.awaiting_retry_response:
            return "abstain"
        if (self.budget_ns <= 0 or self.max_probes <= 0
                or now_ns < self.failed.response_ns
                or now_ns >= self._deadline_ns
                or read.completed_ns > now_ns or self.probes >= self.max_probes):
            self.terminal = True
            return "abstain"
        self.probes += 1
        verdict = verify(self.intent, self.failed, read, self.seen_requests)
        self.seen_requests.add(read.request_id)
        if verdict == "present":
            self.terminal = True
            return "committed"
        if verdict == "absent" and not self.retry_used:
            self.retry_used = True
            self.awaiting_retry_response = True
            return "retry_once"
        if verdict == "absent" or self.probes >= self.max_probes:
            self.terminal = True
            return "abstain"
        return "probe_again"
