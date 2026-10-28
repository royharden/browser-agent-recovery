"""Scheduled paired contrasts; descriptive uncertainty, never acceptance evidence.

Differences are R23 minus comparator: negative harm difference favours R23.
Complete-valid observations alone enter point estimates. Missing observations remain
in scheduled denominators and identification bounds. Bootstrap units are whole
(family, variant) clusters, shared across every condition and arm within a stratum.
No model-quality, independence, significance or overall-superiority claim is made.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import math
import random
import statistics


_GROUP = ("mode", "stage", "model", "source_kind", "condition")
_STATUSES = {"valid", "incomplete", "harness_unknown", "not_executed"}
_SOURCES = {"authored", "scripted", "mock", "live"}
_PRIMARY = {"EXPIRED_VIEW", "STALE_ID"}


def _quantile(values: list, p: float):
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * p
    left = int(position)
    right = min(left + 1, len(ordered) - 1)
    return ordered[left] + (ordered[right] - ordered[left]) * (position - left)


def _distribution(values: list) -> dict:
    return {"n": len(values), "median": statistics.median(values) if values else None,
            "q1": _quantile(values, .25), "q3": _quantile(values, .75)}


def _observed(row: dict | None, metric: str):
    return row[metric] if row is not None and row["status"] == "valid" else None


def _range(row: dict | None, metric: str) -> tuple[int, int]:
    value = _observed(row, metric)
    if value is not None:
        return int(value), int(value)
    # A documented harm remains a known lower bound despite partial evidence.
    if metric == "harm" and row is not None and row["status"] != "not_executed" and row[metric] is True:
        return 1, 1
    return 0, 1


def _binary(pairs: list, metric: str) -> dict:
    complete = []
    low = high = 0
    known = [0, 0]
    unknown = [0, 0]
    for a, b in pairs:
        av, bv = _observed(a, metric), _observed(b, metric)
        if av is not None and bv is not None:
            complete.append((int(av), int(bv)))
        ar, br = _range(a, metric), _range(b, metric)
        low += ar[0] - br[1]
        high += ar[1] - br[0]
        for i, bounds in enumerate((ar, br)):
            known[i] += bounds[0]
            unknown[i] += int(bounds[0] != bounds[1])
    n = len(pairs)
    # b: R23 positive/comparator negative; c: reverse. Thus RD=(b-c)/n.
    b_count = sum(a == 1 and b == 0 for a, b in complete)
    c_count = sum(a == 0 and b == 1 for a, b in complete)
    discordant = b_count + c_count
    p_exact = None
    if complete:
        if not discordant:
            p_exact = 1.0
        else:
            tail = min(b_count, c_count)
            # Integer ratios avoid casting huge binomial coefficients to float.
            p_exact = min(1.0, 2 * (sum(math.comb(discordant, k) for k in range(tail + 1)) / (1 << discordant)))
    return {"scheduled_pairs": n, "complete_valid_pairs": len(complete),
            "coverage": len(complete) / n if n else None,
            "b_r23_only": b_count, "c_comparator_only": c_count,
            "paired_difference": (b_count - c_count) / len(complete) if complete else None,
            "scheduled_difference_bounds": [low / n, high / n] if n else None,
            "known_positive": {"R23": known[0], "comparator": known[1]},
            "unknown_outcome": {"R23": unknown[0], "comparator": unknown[1]},
            "scheduled_positive_rate_bounds": {
                "R23": [known[0] / n, (known[0] + unknown[0]) / n] if n else None,
                "comparator": [known[1] / n, (known[1] + unknown[1]) / n] if n else None},
            "mcnemar_exact_two_sided_descriptive": p_exact}


def _money(value, label: str):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a decimal string or None")
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"invalid {label}") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"invalid {label}")
    return amount


def _cost_summary(pairs: list) -> dict:
    totals = []
    arm_summaries = []
    for position in (0, 1):
        lower = Decimal(0)
        unresolved = Decimal(0)
        unknown_count = unresolved_unknown_count = missing_count = 0
        settled = []
        for pair in pairs:
            row = pair[position]
            cost = row["cost"] if row is not None else {}
            state = cost.get("state")
            amount = _money(cost.get("known_usd"), "known_usd")
            exposure = _money(cost.get("unresolved_usd"), "unresolved_usd")
            if amount is not None:
                lower += amount
            else:
                missing_count += 1
            if exposure is not None:
                unresolved += exposure
            if state == "reserved_unsettled" and exposure is None:
                unresolved_unknown_count += 1
            is_known = state in {"known", "known_zero"} and amount is not None
            if state == "known_zero" and amount != Decimal(0):
                raise ValueError("known_zero requires explicit known_usd='0'")
            if not is_known:
                unknown_count += 1
            settled.append(amount if is_known else None)
        totals.append(settled)
        arm_summaries.append({"known_lower_bound_usd": str(lower) if pairs and missing_count < len(pairs) else None,
                              "unknown_cost_count": unknown_count,
                              "missing_known_amount_count": missing_count,
                              "unresolved_known_usd": str(unresolved) if any(
                                  p[position] is not None and p[position]["cost"].get("unresolved_usd") is not None
                                  for p in pairs) else None,
                              "unresolved_unknown_count": unresolved_unknown_count})
    deltas = [a - b for a, b in zip(*totals) if a is not None and b is not None]
    return {"R23": arm_summaries[0], "comparator": arm_summaries[1],
            "known_paired_cost_count": len(deltas),
            "mean_incremental_usd": str(sum(deltas, Decimal(0)) / len(deltas)) if deltas else None,
            "incremental_cost_scope": "settled known pairs only; unknown liability never zero"}


def contrasts(rows: list[dict], *, bootstrap_seed: int = 0, resamples: int = 10000) -> list[dict]:
    """Return overall and per-family scheduled R23-R1/R0 contrast dictionaries.

    Required row fields are the schedule join contract. No rows are inferred from
    observed execution alone: callers must supply the full scheduled-arm join.
    A missing arm within a represented block is retained as unknown. Block IDs
    must map globally to one family/variant; each group/block/arm occurs once.
    Bootstrap intervals condition on complete-valid outcomes, with denominator-
    zero replicates omitted and explicitly counted. Identification bounds instead
    cover every scheduled pair. Empty coverage is unavailable, never PASS.
    """
    if type(bootstrap_seed) is not int or type(resamples) is not int or resamples < 1:
        raise ValueError("seed must be int and resamples must be positive int")
    if not isinstance(rows, list):
        raise ValueError("rows must be a full scheduled-row list")
    groups = defaultdict(dict)
    clusters = defaultdict(set)
    clean_rows = {}
    block_identity = {}
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each scheduled row must be a dictionary")
        for name in ("schedule_id", "block_id", "variant", "family", "condition", "arm", "mode", "stage", "model", "source_kind", "status"):
            if not isinstance(row.get(name), str) or not row[name]:
                raise ValueError(f"{name} must be a nonempty string")
        if row["schedule_id"] in seen:
            raise ValueError("duplicate schedule_id")
        seen.add(row["schedule_id"])
        if row["status"] not in _STATUSES or row["source_kind"] not in _SOURCES:
            raise ValueError("invalid status or source_kind")
        for metric in ("harm", "success"):
            if metric not in row or (row[metric] is not None and type(row[metric]) is not bool):
                raise ValueError(f"{metric} must be bool or None")
        duration = row.get("duration_ns")
        if "duration_ns" not in row or (duration is not None and (type(duration) is not int or duration < 0)):
            raise ValueError("duration_ns must be nonnegative int or None")
        if not isinstance(row.get("cost"), dict):
            raise ValueError("cost must be a dictionary")
        cost = row["cost"]
        if cost.get("state") not in {None, "known_zero", "known", "unknown", "reserved_unsettled"}:
            raise ValueError("invalid cost state")
        amount = _money(cost.get("known_usd"), "known_usd")
        _money(cost.get("unresolved_usd"), "unresolved_usd")
        if cost.get("state") == "known_zero" and amount != Decimal(0):
            raise ValueError("known_zero requires explicit known_usd='0'")
        identity = row["family"], row["variant"]
        if block_identity.setdefault(row["block_id"], identity) != identity:
            raise ValueError("block_id crosses family/variant")
        key = tuple(row[name] for name in _GROUP)
        arms = groups[key].setdefault(row["block_id"], {})
        if row["arm"] in arms:
            raise ValueError("duplicate arm in group/block")
        arms[row["arm"]] = row
        clusters[key[:-1]].add(identity)
        if row["condition"].upper() == "CLEAN":
            clean_key = key[:-1] + identity + (row["arm"],)
            if clean_key in clean_rows:
                raise ValueError("ambiguous clean counterpart for family/variant/arm")
            clean_rows[clean_key] = row

    # One reproducible bootstrap draw per base stratum, reused by every condition,
    # comparator and family breakdown. Conditions never become independent units.
    rng = random.Random(bootstrap_seed)
    draws = {}
    for base in sorted(clusters):
        population = sorted(clusters[base])
        draws[base] = [Counter(rng.choices(population, k=len(population))) for _ in range(resamples)]
    result = []
    for key in sorted(groups):
        blocks = groups[key]
        condition = key[-1]
        families = sorted({block_identity[b][0] for b in blocks})
        for family in [None, *families]:
            selected = sorted(b for b in blocks if family is None or block_identity[b][0] == family)
            for comparator in ("R1", "R0"):
                pairs = [(blocks[b].get("R23"), blocks[b].get(comparator)) for b in selected]
                role = "descriptive"
                if condition in _PRIMARY:
                    role = "primary" if comparator == "R1" else "secondary"
                if family is not None:
                    role += "_family_breakdown"
                item = dict(zip(_GROUP, key))
                item.update({"family": family, "contrast": f"R23-{comparator}", "analysis_role": role,
                             "stratum": condition, "interpretation": "controller_mechanism_descriptive" if condition == "INTERRUPTED_ACTION" else "condition_specific",
                             "uncertainty": "descriptive; no model-result or significance claim",
                             "availability": "unavailable" if not any(_observed(a, "harm") is not None and _observed(b, "harm") is not None for a, b in pairs) else "observed_pairs_only",
                             "harm": _binary(pairs, "harm"), "success": _binary(pairs, "success")})
                item["arm_status_counts"] = {}
                for position, arm in ((0, "R23"), (1, comparator)):
                    counts = Counter(p[position]["status"] if p[position] is not None else "missing_arm" for p in pairs)
                    item["arm_status_counts"][arm] = {s: counts[s] for s in sorted(_STATUSES | {"missing_arm"})}
                for metric in ("harm", "success"):
                    samples = []
                    for draw in draws[key[:-1]]:
                        numerator = denominator = 0
                        for block, (a, b) in zip(selected, pairs):
                            av, bv = _observed(a, metric), _observed(b, metric)
                            if av is not None and bv is not None:
                                weight = draw[block_identity[block]]
                                numerator += weight * (int(av) - int(bv))
                                denominator += weight
                        if denominator:
                            samples.append(numerator / denominator)
                    item[metric]["block_bootstrap_95_interval"] = [_quantile(samples, .025), _quantile(samples, .975)] if samples else None
                    item[metric]["bootstrap"] = {"seed": bootstrap_seed, "requested_resamples": resamples,
                                                "usable_resamples": len(samples), "empty_resamples": resamples - len(samples),
                                                "unit": "family+variant, all conditions and arms together"}
                durations = [a["duration_ns"] - b["duration_ns"] for a, b in pairs
                             if a is not None and b is not None and a["status"] == b["status"] == "valid"
                             and a["duration_ns"] is not None and b["duration_ns"] is not None]
                item["paired_duration_difference_ns"] = _distribution(durations)
                item["within_arm_excess_vs_clean_ns"] = {}
                for position, arm in ((0, "R23"), (1, comparator)):
                    excess = []
                    if condition.upper() != "CLEAN":
                        for block, pair in zip(selected, pairs):
                            # Schedule block IDs include condition; clean has a
                            # distinct block ID but the same family/variant/arm.
                            clean_key = key[:-1] + block_identity[block] + (arm,)
                            row, clean = pair[position], clean_rows.get(clean_key)
                            if row is not None and clean is not None and row["status"] == clean["status"] == "valid" and row["duration_ns"] is not None and clean["duration_ns"] is not None:
                                excess.append(row["duration_ns"] - clean["duration_ns"])
                    item["within_arm_excess_vs_clean_ns"][arm] = _distribution(excess)
                item["cost"] = _cost_summary(pairs)
                result.append(item)
    return result
