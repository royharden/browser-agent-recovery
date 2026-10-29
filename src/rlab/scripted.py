"""Authored development solver using only the public actor action surface.

This is neither independent reference truth nor a success oracle. It recognizes
three explicit goal grammars, takes one original mutation action, and leaves
recovery to the selected executor arm. No browser or authority is constructed.
"""
from dataclasses import dataclass
import re
from typing import Literal, Protocol

from .actions import Action, Mutation
from .contracts import HistoryRead, PublicTask, Target
from .snapshot import Snapshot, validate_snapshot

ScriptedArm = Literal["R0", "R1", "R2", "R3", "R23"]


class PublicSession(Protocol):
    """Actor-visible facade only; no adapter/driver/authority access."""
    public: PublicTask

    def start(self) -> object: ...
    def observe(self) -> Snapshot: ...
    def history(self) -> HistoryRead: ...
    def act(self, action: Action, arm: ScriptedArm = "R0") -> object: ...


@dataclass(frozen=True)
class ScriptedOutcome:
    """Construction provenance; authored does not mean the task succeeded."""
    status: Literal["authored", "unsupported", "unavailable"]
    goal: str
    reason: str
    original_mutation: Mutation | None = None
    action_result: object | None = None
    finish_receipt: object | None = None
    provenance: str = "authored_scripted"
    validation: str = "runtime_unverified"


@dataclass(frozen=True)
class _Goal:
    operation: Literal["order", "ticket", "delete"]
    target_id: str
    row: str
    button_name: str
    payload: tuple[tuple[str, str], ...]


def _parse_goal(goal: str) -> _Goal | None:
    # These are development goal syntax, not a family/fixture lookup or answer
    # map. Target and body come verbatim from the user-visible goal.
    match = re.fullmatch(r"Order (widget-[0-9]+), quantity 1\.", goal)
    if match:
        item = match.group(1)
        return _Goal("order", item, item, "Order", (("quantity", "1"),))
    match = re.fullmatch(r"Create one support ticket in general with body (widget-[0-9]+)\.", goal)
    if match:
        return _Goal("ticket", "general", "general", "Create ticket", (("body", match.group(1)),))
    match = re.fullmatch(r"Delete exactly (widget-[0-9]+)\.", goal)
    if match:
        item = match.group(1)
        return _Goal("delete", item, item, "Delete", ())
    return None


def _unique(snapshot: Snapshot, role: str, name: str, row: str) -> Target | None:
    matches = [target for target in snapshot.targets
               if (target.role, target.name, target.row_context) == (role, name, row)]
    return matches[0] if len(matches) == 1 else None


def _version(session: PublicSession, snapshot: Snapshot) -> int | None:
    if snapshot.served_version is not None:
        return snapshot.served_version
    # A missing version never becomes zero by default. The ordinary history
    # surface must establish a complete current public version before dispatch.
    history = session.history()
    if (not isinstance(history, HistoryRead)
            or (history.run_id, history.epoch) != (snapshot.run_id, snapshot.epoch)
            or not history.clock_id or not history.request_id
            or not history.successful or not history.complete or not history.unfiltered
            or history.cached or history.aliases
            or type(history.served_version) is not int or history.served_version < 0
            or type(history.latest_version) is not int
            or history.served_version != history.latest_version
            or type(history.started_ns) is not int or type(history.completed_ns) is not int
            or not 0 <= history.started_ns <= history.completed_ns):
        return None
    return history.served_version


def run_scripted(session: PublicSession, arm: ScriptedArm = "R0") -> ScriptedOutcome:
    """Run one authored F1/F2/F3 goal without inspecting hidden task state.

    Call with a new public session. Acknowledged start/fill/finish receipts are
    interaction evidence only. An unavailable outcome after mutation dispatch
    explicitly retains uncertainty; it must never justify another submission.
    """
    goal = session.public.goal
    parsed = _parse_goal(goal)
    if parsed is None:
        return ScriptedOutcome("unsupported", goal, "unsupported explicit development goal")
    if arm not in {"R0", "R1", "R2", "R3", "R23"}:
        return ScriptedOutcome("unsupported", goal, "unsupported recovery arm")
    original = None
    action_result = None
    dispatched = False
    try:
        start = session.start()
        if getattr(start, "status", None) != "acknowledged":
            return ScriptedOutcome("unavailable", goal, "task start not acknowledged")
        snapshot = validate_snapshot(session.observe(), session.public.run_id, session.public.epoch)
        button = _unique(snapshot, "button", parsed.button_name, parsed.row)
        if button is None:
            return ScriptedOutcome("unavailable", goal, "visible mutation button missing or ambiguous")
        if parsed.operation == "ticket":
            body = _unique(snapshot, "textbox", "Body", parsed.row)
            if body is None:
                return ScriptedOutcome("unavailable", goal, "visible Body textbox missing or ambiguous")
            filled = session.act(Action("fill", ref=body.ref, snapshot_epoch=snapshot.snapshot_epoch,
                                        value=dict(parsed.payload)["body"]), arm)
            if getattr(filled, "status", None) != "acknowledged":
                return ScriptedOutcome("unavailable", goal, "Body fill not acknowledged")
            # Fill may change references. Resolve only the original semantic row
            # and button again, without changing the original goal/form fields.
            snapshot = validate_snapshot(session.observe(), session.public.run_id, session.public.epoch)
            button = _unique(snapshot, "button", parsed.button_name, parsed.row)
            if button is None:
                return ScriptedOutcome("unavailable", goal, "mutation button missing or ambiguous after fill")
        version = _version(session, snapshot)
        if version is None:
            return ScriptedOutcome("unavailable", goal, "current public pre-action version unavailable")
        original = Mutation(parsed.operation, parsed.target_id, parsed.payload, version)
        dispatched = True
        action_result = session.act(Action("click", ref=button.ref,
                                          snapshot_epoch=snapshot.snapshot_epoch, intent=original), arm)
        finish = session.act(Action("finish"), arm)
        return ScriptedOutcome("authored", goal,
                               "authored mutation returned; finish is termination, not oracle success",
                               original, action_result, finish)
    except Exception as exc:
        # A failed bridge or cap cannot be converted into success or absence.
        # Do not retry here: the executor owns the arm's bounded retry policy.
        uncertainty = "; mutation outcome uncertain, do not resubmit" if dispatched else ""
        return ScriptedOutcome("unavailable", goal,
                               "public session unavailable: " + type(exc).__name__ + uncertainty,
                               original, action_result)
