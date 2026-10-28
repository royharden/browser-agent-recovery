"""Canonical immutable public records; no controller, port or authority access.

Legacy executor/ports exports alias these exact classes. Field/default/decorator
shapes are preserved; class __module__ now names rlab.public_records.
"""
from dataclasses import dataclass
from typing import Literal

from .contracts import Origin

Arm = Literal["R0", "R1", "R2", "R3", "R23"]
Disposition = Literal["acknowledged", "committed", "returned", "abstained", "cap_abort", "harness_unknown"]


@dataclass(frozen=True)
class ActionReceipt:
    request_id: str
    run_id: str
    epoch: str
    clock_id: str
    response_ns: int
    status: Literal["acknowledged", "failed", "unchanged", "unknown"]
    error: str = ""


@dataclass(frozen=True)
class InteractionReceipt:
    """Trusted browser interaction timing; not a server mutation/effect event."""
    request_id: str
    run_id: str
    epoch: str
    clock_id: str
    response_ns: int
    status: Literal["acknowledged", "unknown"]
    url: str
    error: str = ""


@dataclass(frozen=True)
class Step:
    kind: str
    request_id: str
    origin: Origin
    started_ns: int
    completed_ns: int
    outcome: str


@dataclass(frozen=True)
class ExecutionResult:
    root_intent_id: str
    arm: Arm
    disposition: Disposition
    receipts: tuple[ActionReceipt, ...]
    steps: tuple[Step, ...]
    reason: str = ""
    cancelled_request_ids: tuple[str, ...] = ()
    pending_cleanup_request_ids: tuple[str, ...] = ()
    uncertain_request_ids: tuple[str, ...] = ()
    request_id: str = ""


__all__ = ["Arm", "Disposition", "ActionReceipt", "InteractionReceipt", "Step", "ExecutionResult"]
