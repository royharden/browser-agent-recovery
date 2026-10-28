"""Canonical hashes and externally anchored report inputs; no signature claims."""
import hashlib
import json
import re
from pathlib import Path

PIN_KEYS = {"source", "schedule", "oracle", "config", "price"}


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def pins_valid(pins: dict) -> None:
    if set(pins) != PIN_KEYS or any(
            not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in pins.values()):
        raise ValueError("source/schedule/oracle/config/price SHA256 pins required")


def require_pins(actual: dict, expected: dict) -> None:
    pins_valid(actual)
    pins_valid(expected)
    if actual != expected:
        raise ValueError("frozen pin mismatch")


def implementation_pins() -> dict:
    """Read only this evaluator and its two standalone entrypoints.

    A hash inventory is provenance, not permission, authorship or acceptance.
    Callers must compare to their external frozen pins before any study use.
    """
    root = Path(__file__).resolve().parent.parent
    paths = sorted((root / "evaluation").glob("*.py"))
    paths += [root / "scripts" / name for name in ("report.py", "verify_report.py")]
    inventory = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in paths}
    return {"source": digest(inventory), "oracle": inventory["evaluation/oracle.py"]}


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def load_json(text: str) -> object:
    def reject_constant(value: str) -> None:
        raise ValueError("non-finite JSON number: " + value)
    return json.loads(text, object_pairs_hook=_unique_object,
                      parse_constant=reject_constant)
