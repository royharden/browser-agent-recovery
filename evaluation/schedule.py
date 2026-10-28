"""Validate externally frozen schedule labels, never author hidden instances."""
from .freeze import digest

FIELDS = {"schedule_id", "block_id", "variant", "family", "condition", "arm",
          "mode", "stage", "model", "source_kind"}
CONDITIONS = {"clean", "EXPIRED_VIEW", "STALE_ID", "INTERRUPTED_ACTION"}
ARMS = {"R0", "R1", "R2", "R3", "R23", "RP"}


def validate_schedule(rows: list[dict]) -> list[dict]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty frozen schedule required")
    ids, cells, blocks = set(), set(), {}
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError("closed schedule fields required")
        if any(not isinstance(value, str) or not value.strip() for value in row.values()):
            raise ValueError("nonempty schedule labels required")
        if row["condition"] not in CONDITIONS or row["arm"] not in ARMS:
            raise ValueError("unsupported condition/arm metadata")
        if row["source_kind"] not in {"authored", "scripted", "mock", "live"}:
            raise ValueError("unknown source kind")
        if row["mode"] not in {"fixture", "live"} or (
                (row["source_kind"] == "live") != (row["mode"] == "live")):
            raise ValueError("live and fixture provenance cannot be mixed")
        if row["schedule_id"] in ids:
            raise ValueError("duplicate scheduled row")
        ids.add(row["schedule_id"])
        group = tuple(row[k] for k in ("mode", "stage", "model", "source_kind", "block_id"))
        identity = tuple(row[k] for k in ("family", "variant", "condition"))
        if group in blocks and blocks[group] != identity:
            raise ValueError("block identity changes between arms")
        blocks[group] = identity
        cell = group + (row["arm"],)
        if cell in cells:
            raise ValueError("duplicate block/arm")
        cells.add(cell)
        result.append(dict(row))
    return result


def schedule_digest(rows: list[dict]) -> str:
    return digest(validate_schedule(rows))
