"""Closed actor commands. Validation checks syntax, never semantic identity."""
from dataclasses import dataclass
from typing import Literal, Mapping

from .contracts import Operation

ActionKind = Literal["click", "fill", "select", "goto", "back", "reload", "wait", "finish"]


def text(value: object, label: str, limit: int, *, empty: bool = False) -> str:
    if (not isinstance(value, str) or (not empty and not value)
            or len(value) > limit or any(ord(c) < 32 for c in value)):
        raise ValueError("invalid " + label)
    return value


@dataclass(frozen=True)
class Mutation:
    """Goal/original-action intent, never private expected-effect metadata."""
    operation: Operation
    target_id: str
    payload: tuple[tuple[str, str], ...]
    before_version: int


@dataclass(frozen=True)
class Action:
    kind: ActionKind
    ref: str = ""
    snapshot_epoch: str = ""
    value: str = ""
    path: str = ""
    duration_ms: int = 0
    intent: Mutation | None = None


def parse_action(raw: Mapping[str, object]) -> Action:
    """Reject extras, loose numeric coercions, uploads and arbitrary tools."""
    if not isinstance(raw, dict) or type(raw.get("kind")) is not str:
        raise ValueError("closed action object required")
    kind = raw["kind"]
    fields = {
        "click": {"kind", "ref", "snapshot_epoch"},
        "fill": {"kind", "ref", "snapshot_epoch", "value"},
        "select": {"kind", "ref", "snapshot_epoch", "value"},
        "goto": {"kind", "path"}, "back": {"kind"}, "reload": {"kind"},
        "wait": {"kind", "duration_ms"}, "finish": {"kind"},
    }
    if kind not in fields:
        raise ValueError("unknown action kind")
    expected = fields[kind] | ({"intent"} if kind == "click" and "intent" in raw else set())
    if set(raw) != expected:
        raise ValueError("missing or extra action fields")
    ref = text(raw["ref"], "reference", 160) if "ref" in raw else ""
    epoch = text(raw["snapshot_epoch"], "snapshot epoch", 160) if "snapshot_epoch" in raw else ""
    value = text(raw["value"], "field value", 4096, empty=True) if "value" in raw else ""
    path = text(raw["path"], "path", 512) if "path" in raw else ""
    duration = raw.get("duration_ms", 0)
    if type(duration) is not int or not 0 <= duration <= 3000:
        raise ValueError("bounded integer wait required")
    mutation = None
    if "intent" in raw:
        m = raw["intent"]
        if not isinstance(m, dict) or set(m) != {"operation", "target_id", "payload", "before_version"}:
            raise ValueError("closed public mutation intent required")
        if m["operation"] not in {"order", "ticket", "delete"}:
            raise ValueError("unsupported development operation")
        target_id = text(m["target_id"], "public target", 256)
        version = m["before_version"]
        payload = m["payload"]
        if (type(version) is not int or version < 0 or not isinstance(payload, dict)
                or len(payload) > 8):
            raise ValueError("invalid public version or form fields")
        pairs = tuple(sorted((text(k, "field name", 64), text(v, "field value", 4096, empty=True))
                             for k, v in payload.items()))
        if any(k in {"ref", "snapshot"} for k, _ in pairs):
            raise ValueError("reserved form field")
        mutation = Mutation(m["operation"], target_id, pairs, version)
    return Action(kind, ref, epoch, value, path, duration, mutation)


def validate_action(action: Action) -> Action:
    """Use the same closed parser for dataclass callers and JSON callers."""
    if not isinstance(action, Action):
        raise ValueError("Action required")
    raw: dict[str, object] = {"kind": action.kind}
    if action.kind in {"click", "fill", "select"}:
        raw.update(ref=action.ref, snapshot_epoch=action.snapshot_epoch)
    if action.kind in {"fill", "select"}:
        raw["value"] = action.value
    if action.kind == "goto":
        raw["path"] = action.path
    if action.kind == "wait":
        raw["duration_ms"] = action.duration_ms
    if action.intent is not None:
        if not isinstance(action.intent, Mutation):
            raise ValueError("invalid intent object")
        if len(dict(action.intent.payload)) != len(action.intent.payload):
            raise ValueError("duplicate public payload fields")
        raw["intent"] = {"operation": action.intent.operation, "target_id": action.intent.target_id,
                         "payload": dict(action.intent.payload), "before_version": action.intent.before_version}
    parsed = parse_action(raw)
    if parsed != action:
        raise ValueError("unused or noncanonical action fields")
    return parsed
