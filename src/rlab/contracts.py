"""Public actor contracts; no private task answers or authority handles."""
from dataclasses import dataclass
from typing import Literal

Operation = Literal["order", "ticket", "delete"]
Origin = Literal["agent_direct", "controller_retry", "controller_resolve"]


@dataclass(frozen=True)
class PublicTask:
    run_id: str
    epoch: str
    goal: str
    start_path: str
    max_actions: int = 40


@dataclass(frozen=True)
class Target:
    ref: str
    snapshot_epoch: str
    role: str
    name: str
    row_context: str


@dataclass(frozen=True)
class Intent:
    root_intent_id: str
    operation: Operation
    target_id: str
    payload: tuple[tuple[str, str], ...]
    target: Target
    before_version: int


@dataclass(frozen=True)
class Transition:
    operation: Operation
    target_id: str
    payload: tuple[tuple[str, str], ...]
    state_version: int


@dataclass(frozen=True)
class HistoryRead:
    """Trusted driver timing + ordinary public history, never server event log."""
    run_id: str
    epoch: str
    clock_id: str
    request_id: str
    started_ns: int
    completed_ns: int
    served_version: int | None
    latest_version: int | None
    transitions: tuple[Transition, ...]
    successful: bool = True
    complete: bool = True
    unfiltered: bool = True
    cached: bool = False
    aliases: bool = False


@dataclass(frozen=True)
class FailedAction:
    run_id: str
    epoch: str
    clock_id: str
    response_ns: int
