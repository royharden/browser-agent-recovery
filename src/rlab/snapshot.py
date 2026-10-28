"""Bounded public snapshots. Ref validation does not add an R3 identity guard."""
from dataclasses import dataclass

from .actions import Action, text, validate_action
from .contracts import Target


@dataclass(frozen=True)
class Snapshot:
    run_id: str
    epoch: str
    snapshot_epoch: str
    url: str
    targets: tuple[Target, ...]
    body: str
    served_version: int | None = None


def validate_snapshot(snapshot: Snapshot, run_id: str, epoch: str) -> Snapshot:
    if not isinstance(snapshot, Snapshot) or (snapshot.run_id, snapshot.epoch) != (run_id, epoch):
        raise ValueError("snapshot run/epoch mismatch")
    text(snapshot.snapshot_epoch, "snapshot epoch", 160)
    text(snapshot.url, "snapshot URL", 768)
    if not isinstance(snapshot.body, str) or len(snapshot.body.encode("utf-8")) > 16384:
        raise ValueError("snapshot body exceeds cap; truncation forbidden")
    if not isinstance(snapshot.targets, tuple) or len(snapshot.targets) > 64:
        raise ValueError("snapshot reference cap")
    refs: set[str] = set()
    size = len(snapshot.body.encode("utf-8"))
    for target in snapshot.targets:
        if not isinstance(target, Target) or target.snapshot_epoch != snapshot.snapshot_epoch:
            raise ValueError("invalid target snapshot epoch")
        for value, label, cap in ((target.ref, "ref", 160), (target.role, "role", 64),
                                  (target.name, "name", 256), (target.row_context, "row", 512)):
            text(value, label, cap, empty=label in {"name", "row"})
            size += len(value.encode("utf-8"))
        if target.ref in refs:
            raise ValueError("duplicate snapshot reference")
        refs.add(target.ref)
    if size > 32768 or (snapshot.served_version is not None and (
            type(snapshot.served_version) is not int or snapshot.served_version < 0)):
        raise ValueError("snapshot size/version rejected")
    return snapshot


def referenced_target(action: Action, snapshot: Snapshot) -> Target | None:
    validate_action(action)
    if action.kind not in {"click", "fill", "select"}:
        return None
    if action.snapshot_epoch != snapshot.snapshot_epoch:
        raise ValueError("action did not cite its captured snapshot")
    matches = [target for target in snapshot.targets if target.ref == action.ref]
    if len(matches) != 1:
        raise ValueError("unknown captured reference")
    expected_role = {"click": {"button"}, "fill": {"textbox", "spinbutton"},
                     "select": {"combobox"}}[action.kind]
    if matches[0].role not in expected_role:
        raise ValueError("captured control does not support that action")
    # Do not compare against a newly fetched DOM here. R0/R1 must remain exposed
    # to syntactically valid silent remaps; only R3/R23 refresh semantic identity.
    return matches[0]
