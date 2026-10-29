"""Original F1/F2/F3 development schedule metadata, never private task truth.

Generating a schedule is not executing it or admitting its data. All source
labels describe authored development instruments, never live model quality.
"""
from __future__ import annotations

import hashlib

from .freeze import digest
from .schedule import validate_schedule

FAMILIES = ("F1", "F2", "F3")
CONDITIONS = ("clean", "EXPIRED_VIEW", "STALE_ID", "INTERRUPTED_ACTION")
PROFILES = {
    "scripted": ("R0", "R1", "R2", "R3", "R23"),
    "naive": ("R0",),
    "lag": ("R2", "R23"),
    "offline": ("R0", "R1", "R23", "RP"),
    "planted-parser": ("R2", "R23"),
    "misconfigured": ("R2", "R23"),
}


def development_matrix(profile: str, *, order_seed: int = 0,
                       offline_source: str = "mock") -> dict:
    """Return canonical schedule plus sidecar; diagnostic profiles are separate.

    SHA256-ranked block then arm ordering is declared and platform-independent.
    Seed pairs task/fault boundary across arms; it does not pair model randomness.
    RP remains scheduled but unavailable: no adapted/licensed prompt is supplied.
    """
    if profile not in PROFILES or type(order_seed) is not int or order_seed < 0:
        raise ValueError("known development profile and nonnegative ordering seed required")
    if offline_source not in {"mock", "authored"}:
        raise ValueError("offline source must be mock or authored")
    source = offline_source if profile == "offline" else "scripted"
    stage = {"scripted": "dev-scripted", "naive": "diagnostic-naive-reclicker",
             "lag": "diagnostic-lag-grid", "offline": "dev-offline",
             "planted-parser": "diagnostic-planted-parser",
             "misconfigured": "diagnostic-misconfigured"}[profile]
    combos = ((0, 1), (0, 4), (2, 1), (2, 4)) if profile in {
        "lag", "planted-parser", "misconfigured"} else ((2, 4),)
    conditions = ("INTERRUPTED_ACTION",) if len(combos) > 1 else CONDITIONS
    rows, metadata = [], {}
    for family in FAMILIES:
        for seed in range(20):
            for condition in conditions:
                for lag, budget in combos:
                    variant = f"dev-seed-{seed:02d}"
                    block = f"{profile}-{source}-{family}-{variant}-{condition}-L{lag}-B{budget}"
                    boundary = digest({"family": family, "seed": seed,
                                       "condition": condition, "boundary": "first-eligible-mutation"})
                    for arm in PROFILES[profile]:
                        row_id = f"{block}-{arm}"
                        rows.append({"schedule_id": row_id, "block_id": block,
                                     "variant": variant, "family": family,
                                     "condition": condition, "arm": arm, "mode": "fixture",
                                     "stage": stage, "model": "offline-" + source,
                                     "source_kind": source})
                        metadata[row_id] = {
                            "seed": seed, "task_block": f"{family}-{variant}",
                            "fault_boundary": "none" if condition == "clean" else "first-eligible-mutation",
                            "fault_pair_sha256": boundary,
                            "lag_ns": lag * 1_000_000_000,
                            "reconcile_budget_ns": budget * 1_000_000_000,
                            "control": condition == "clean", "profile": profile,
                            "lineage": "original-development-metadata-v1",
                            "parser": "watermark-ignoring" if profile == "planted-parser" else "standard",
                            "configuration": "deliberately-misconfigured" if profile == "misconfigured" else "standard",
                            "actor": "naive-reclicker" if profile == "naive" else "profile-default",
                            "availability": "unavailable" if arm == "RP" else "pending-backend",
                            "reason": "RP original/cleared adapted prompt source unavailable" if arm == "RP" else None,
                            "replay_source_cost": {"state": "unknown", "known_usd": None,
                                                   "unresolved_usd": None} if profile == "offline" else None,
                        }

    def rank(label: str) -> str:
        return hashlib.sha256(f"m18-matrix-order-v1:{order_seed}:{label}".encode("ascii")).hexdigest()

    rows.sort(key=lambda row: (rank(row["block_id"]), row["block_id"],
                               rank(row["schedule_id"]), row["schedule_id"]))
    return {"schema": "rlab.development-matrix.v1", "profile": profile,
            "order_seed": order_seed, "offline_source": offline_source,
            "ordering": "sha256-block-then-arm-v1", "schedule": validate_schedule(rows),
            "metadata": metadata}


def validate_matrix(matrix: dict) -> dict:
    """Require the exact original development generator output, not hidden rows."""
    if not isinstance(matrix, dict):
        raise ValueError("matrix object required")
    expected = development_matrix(matrix.get("profile"), order_seed=matrix.get("order_seed"),
                                  offline_source=matrix.get("offline_source"))
    if digest(matrix) != digest(expected):
        raise ValueError("matrix metadata/order/row identity differs from declared generator")
    return expected
