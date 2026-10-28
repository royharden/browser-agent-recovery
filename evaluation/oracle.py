"""Sealed-map adapter and original generic oracle; independent truth is external.

Integrity is checked before scoring. These functions never open an authority DB
or invent expected answers. Independent challenge/arithmetic admission is pending.
"""
from collections import Counter

from .freeze import canonical, digest, load_json


def integer(value: object, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError("invalid integer: " + name)
    return value


def signature(effect: dict) -> str:
    return canonical({"kind": effect["kind"], "target": effect["target"],
                      "payload": effect["payload"]})


def _payload(text: str) -> dict:
    value = load_json(text)
    if not isinstance(value, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()):
        raise ValueError("canonical string-field payload required")
    if canonical(value) != text:
        raise ValueError("noncanonical effect payload")
    return value


def _state(rows: list[dict]) -> dict[str, bool]:
    state = {}
    for row in rows:
        if set(row) != {"id", "deleted"} or not isinstance(row["id"], str):
            raise ValueError("invalid state row")
        if row["id"] in state or type(row["deleted"]) not in {int, bool} or row["deleted"] not in (0, 1):
            raise ValueError("duplicate item or invalid deletion flag")
        state[row["id"]] = bool(row["deleted"])
    return state


def validate_seal(seal: dict) -> dict:
    if not isinstance(seal, dict) or set(seal) != {"bundle", "sha256"}:
        raise ValueError("sealed export missing")
    bundle = seal["bundle"]
    if digest(bundle) != seal["sha256"]:
        raise ValueError("export digest mismatch")
    if set(bundle) != {"schema", "run", "effects", "attempts", "state", "fault", "visibility", "terminal"}:
        raise ValueError("unsupported evidence fields")
    if bundle["schema"] != "rlab.evidence.v1":
        raise ValueError("unsupported evidence schema")
    run, terminal = bundle["run"], bundle["terminal"]
    for key in ("run", "epoch", "clock", "family"):
        if not isinstance(run[key], str) or not run[key]:
            raise ValueError("missing run identity")
    if run["sealed"] != 0 or terminal["sealed"] is not True or terminal["clock_id"] != run["clock"]:
        raise ValueError("invalid terminal/clock identity")
    end = integer(terminal["ns"], "terminal.ns")
    version = integer(run["version"], "run.version")
    if version != len(bundle["effects"]):
        raise ValueError("effect count/version mismatch")
    used_attempts, attempts = set(), bundle["attempts"]
    last = 0
    for seq, attempt in enumerate(attempts, 1):
        ns = integer(attempt["ns"], "attempt.ns")
        if (attempt["run"] != run["run"] or attempt["seq"] != seq
                or ns < last or ns > end or not attempt["request"] or not attempt["root"]
                or attempt["origin"] not in {"agent_direct", "controller_retry", "controller_resolve"}):
            raise ValueError("attempt sequence/lineage/clock mismatch")
        _payload(attempt["payload"])
        last = ns
    last, normalized = 0, []
    for seq, effect in enumerate(bundle["effects"], 1):
        ns = integer(effect["ns"], "effect.ns")
        if (effect["run"] != run["run"] or effect["epoch"] != run["epoch"]
                or effect["clock"] != run["clock"] or effect["seq"] != seq
                or effect["version"] != seq or ns < last or ns > end):
            raise ValueError("effect sequence/version/clock mismatch")
        matches = [i for i, attempt in enumerate(attempts)
                   if i not in used_attempts and all(attempt[a] == effect[b] for a, b in (
                       ("request", "request"), ("operation", "kind"), ("target", "target"),
                       ("payload", "payload"), ("ns", "ns")))]
        if not matches:
            raise ValueError("effect has no matching trusted attempt")
        used_attempts.add(matches[0])
        normalized.append({"kind": effect["kind"], "target": effect["target"],
                           "payload": _payload(effect["payload"]), "ns": ns,
                           "version": seq, "origin": attempts[matches[0]]["origin"]})
        last = ns
    _state(bundle["state"])
    fault = bundle["fault"]
    if fault["status"] == "clean":
        if (set(fault) != {"kind", "status", "disposition", "harness_error"}
                or fault["kind"] != "clean" or fault["disposition"] != "not_fired"
                or fault["harness_error"] is not False):
            raise ValueError("invalid clean fault record")
    else:
        if (fault["run"] != run["run"] or fault["epoch"] != run["epoch"]
                or fault["clock"] != run["clock"]
                or fault["kind"] not in {"EXPIRED_VIEW", "STALE_ID", "INTERRUPTED_ACTION"}
                or fault["status"] not in {"armed", "selected", "fired", "not_fired"}):
            raise ValueError("fault identity/state mismatch")
        if set(fault) != {"run", "epoch", "clock", "kind", "boundary", "seen",
                          "selected_request", "status", "onset_ns", "snapshot", "disposition", "harness_error"}:
            raise ValueError("unsupported fault fields")
        boundary = integer(fault["boundary"], "fault.boundary", 1)
        seen = integer(fault["seen"], "fault.seen")
        if fault["status"] == "armed":
            if not seen < boundary or fault["selected_request"] is not None:
                raise ValueError("armed fault cannot have reached/selected boundary")
        elif seen != boundary or not isinstance(fault["selected_request"], str) or not fault["selected_request"]:
            raise ValueError("selected/fired fault must identify the reached boundary")
        if fault["status"] != "fired" and (fault["onset_ns"] is not None or fault["snapshot"] is not None):
            raise ValueError("unfired fault cannot have an onset/snapshot")
        if fault["status"] == "not_fired" and fault["kind"] != "INTERRUPTED_ACTION":
            raise ValueError("only an unissued interruption has cancel disposition")
        if fault["disposition"] != ("fired" if fault["status"] == "fired" else "not_fired"):
            raise ValueError("fault disposition mismatch")
        if fault["harness_error"] is not (fault["status"] == "selected"):
            raise ValueError("fault harness-error mismatch")
        if fault["status"] == "fired":
            if integer(fault["onset_ns"], "fault.onset") > end or not fault["selected_request"] or not fault["snapshot"]:
                raise ValueError("fault onset/selection missing")
    visibility, timing_unknown, last = bundle["visibility"], False, 0
    if len(visibility) != version:
        raise ValueError("visibility count mismatch")
    for seq, stamp in enumerate(visibility, 1):
        if stamp["version"] != seq or stamp["clock_id"] != run["clock"]:
            raise ValueError("visibility clock/version mismatch")
        ns = stamp["committed_ns"]
        if ns is None:
            timing_unknown = True
            continue
        ns = integer(ns, "visibility.committed_ns")
        if ns < max(last, normalized[seq-1]["ns"]) or ns > end:
            raise ValueError("visibility timing mismatch")
        last = ns
    return {"bundle": bundle, "effects": normalized, "timing_unknown": timing_unknown}


def validate_spec(spec: dict) -> None:
    if set(spec) != {"initial_state", "expected_effects", "forbidden_effects", "ordered_effects", "terminal_predicates"}:
        raise ValueError("closed external private specification required")
    _state(spec["initial_state"])
    for effect in spec["expected_effects"] + spec["ordered_effects"]:
        if set(effect) != {"kind", "target", "payload"} or not isinstance(effect["payload"], dict):
            raise ValueError("exact expected/ordered effect signature required")
        signature(effect)
    for pattern in spec["forbidden_effects"]:
        if not isinstance(pattern, dict) or not pattern or not set(pattern) <= {"kind", "target", "payload"}:
            raise ValueError("invalid forbidden-effect pattern")
    initial = _state(spec["initial_state"])
    for predicate in spec["terminal_predicates"]:
        if (set(predicate) != {"item_id", "deleted"} or predicate["item_id"] not in initial
                or type(predicate["deleted"]) is not bool):
            raise ValueError("unsupported exact terminal predicate")


def state_at(spec: dict, effects: list[dict]) -> dict[str, bool]:
    state = _state(spec["initial_state"])
    for effect in effects:
        if effect["kind"] == "delete":
            target = effect["target"]
            if target not in state or state[target]:
                raise ValueError("impossible deletion transition")
            state[target] = True
        elif effect["kind"] not in {"order", "ticket"}:
            raise ValueError("unadmitted state transition adapter")
    return state


def assess(spec: dict, effects: list[dict], state: dict[str, bool]) -> dict:
    expected = Counter(signature(effect) for effect in spec["expected_effects"])
    actual = Counter(signature(effect) for effect in effects)
    duplicate = any(count > max(1, expected[key]) for key, count in actual.items())
    wrong = any(key not in expected for key in actual) or any(
        all(effect.get(key) == value for key, value in pattern.items())
        for pattern in spec["forbidden_effects"] for effect in effects)
    missing = bool(expected - actual)
    position = 0
    ordered = [signature(effect) for effect in spec["ordered_effects"]]
    for effect in effects:
        if position < len(ordered) and signature(effect) == ordered[position]:
            position += 1
    terminal_ok = all(state[p["item_id"]] == p["deleted"] for p in spec["terminal_predicates"])
    exact = actual == expected and not wrong and position == len(ordered) and terminal_ok
    seen, bad_origins = Counter(), Counter()
    for effect in effects:
        key = signature(effect)
        seen[key] += 1
        forbidden = any(all(effect.get(k) == v for k, v in pattern.items())
                        for pattern in spec["forbidden_effects"])
        if key not in expected or seen[key] > expected[key] or forbidden:
            bad_origins[effect.get("origin", "unattributed")] += 1
    return {"success": exact, "duplicate_effect": duplicate, "wrong_effect": wrong,
            "missing_effect": missing, "ordering_satisfied": position == len(ordered),
            "terminal_satisfied": terminal_ok, "harm": duplicate or wrong,
            "bad_effect_origins": dict(bad_origins)}


def score(seal: dict | None, spec: dict | None) -> dict:
    try:
        checked = validate_seal(seal)
        validate_spec(spec)
        state = state_at(spec, checked["effects"])
        if state != _state(checked["bundle"]["state"]):
            raise ValueError("initial/effect/final state mismatch")
        outcome = assess(spec, checked["effects"], state)
        fault = checked["bundle"]["fault"]
        unknown = checked["timing_unknown"] or fault["harness_error"]
        outcome.update(status="harness_unknown" if unknown else "valid",
                       terminal_status="harness_unknown" if unknown else (
                           "success" if outcome["success"] else "incomplete"),
                       timing_unknown=checked["timing_unknown"],
                       fired=fault["kind"] != "clean" and fault["disposition"] == "fired",
                       not_fired=fault["kind"] != "clean" and fault["disposition"] == "not_fired",
                       reason="missing visibility anchor or unfinished fault" if unknown else None)
        if unknown:
            outcome["success"] = None
            if not outcome["harm"]:
                outcome["harm"] = None
        return outcome
    except (ValueError, TypeError, KeyError, IndexError) as error:
        return {"status": "harness_unknown", "terminal_status": "harness_unknown",
                "success": None, "harm": None, "duplicate_effect": None,
                "wrong_effect": None, "missing_effect": None,
                "timing_unknown": True, "not_fired": None, "reason": str(error)}
