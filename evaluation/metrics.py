"""All scheduled rows and all-attempt cost; missing values stay unknown."""
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import statistics

from .failures import labels
from .latency import latency
from .oracle import score, validate_seal


def money(value: object) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("money must be an exact decimal string")
    number = Decimal(value)
    if not number.is_finite() or number < 0:
        raise ValueError("invalid nonnegative money")
    return number


def cost(raw: dict | None, source_kind: str) -> dict:
    try:
        if not isinstance(raw, dict) or set(raw) != {"state", "known_usd", "unresolved_usd"}:
            raise ValueError("missing all-attempt cost receipt")
        state = raw["state"]
        if state not in {"known_zero", "known", "unknown", "reserved_unsettled"}:
            raise ValueError("invalid cost state")
        known, unresolved = money(raw["known_usd"]), money(raw["unresolved_usd"])
        if state in {"known", "known_zero"} and (known is None or unresolved != 0):
            raise ValueError("settled receipt needs known amount and zero liability")
        if state == "known_zero" and (known != 0 or source_kind == "live"):
            raise ValueError("known_zero is keyless current spend only")
        if state == "reserved_unsettled" and unresolved is None:
            raise ValueError("unsettled liability bound missing")
        return {"state": state, "known_usd": None if known is None else str(known),
                "unresolved_usd": None if unresolved is None else str(unresolved), "reason": None}
    except (ValueError, TypeError, InvalidOperation) as error:
        return {"state": "unknown", "known_usd": None, "unresolved_usd": None, "reason": str(error)}


def joined_rows(schedule: list[dict], records: dict[str, dict]) -> list[dict]:
    if set(records)-{row["schedule_id"] for row in schedule}:
        raise ValueError("unscheduled records cannot enter report")
    result = []
    for scheduled in schedule:
        record = records.get(scheduled["schedule_id"])
        if record is None:
            outcome = {"status": "not_executed", "success": None, "harm": None}
            result.append({**scheduled, **outcome, "termination": "not_executed",
                           "outcome": outcome, "cost": cost(None, scheduled["source_kind"]),
                           "duration_ns": None, "latency": None, "actions": None,
                           "model_calls": None, "attempts": None, "failures": ["NOT_EXECUTED"], "media": []})
            continue
        if not isinstance(record, dict) or set(record) != {"seal", "spec", "execution", "cost", "reads", "media"}:
            raise ValueError("closed execution record fields required")
        execution = record["execution"]
        if not isinstance(execution, dict) or set(execution) != {
                "run_id", "epoch", "clock_id", "start_ns", "termination", "actions", "model_calls", "failures"}:
            raise ValueError("closed trusted execution receipt required")
        outcome = score(record["seal"], record["spec"])
        checked = None
        try:
            checked = validate_seal(record["seal"])
            bundle = checked["bundle"]
            if (execution["run_id"] != bundle["run"]["run"]
                    or execution["epoch"] != bundle["run"]["epoch"]
                    or execution["clock_id"] != bundle["run"]["clock"]
                    or scheduled["family"] != bundle["run"]["family"]
                    or scheduled["condition"] != bundle["fault"]["kind"]):
                raise ValueError("schedule/execution/seal identity mismatch")
        except (ValueError, TypeError, KeyError, IndexError) as error:
            outcome = {"status": "harness_unknown", "success": None, "harm": None,
                       "reason": str(error), "timing_unknown": True}
            checked = None
        for key in ("actions", "model_calls"):
            if execution[key] is not None and (type(execution[key]) is not int or execution[key] < 0):
                raise ValueError("invalid execution count")
        times = latency(record["seal"], record["spec"], record["reads"], execution["start_ns"]) if checked else None
        if times and times["reason"] == "invalid or incomplete authority timing":
            outcome = {**outcome, "status": "harness_unknown", "success": None,
                       "harm": True if outcome.get("harm") is True else None, "timing_unknown": True}
        result.append({**scheduled, "status": outcome["status"], "success": outcome["success"],
                       "harm": outcome["harm"], "outcome": outcome, "termination": execution["termination"],
                       "cost": cost(record["cost"], scheduled["source_kind"]),
                       "latency": times, "duration_ns": times["duration_ns"] if times else None,
                       "actions": execution["actions"], "model_calls": execution["model_calls"],
                       "attempts": len(checked["bundle"]["attempts"]) if checked else None,
                       "failures": sorted(set(labels(outcome, execution)) | (
                           {"MISSING_MEDIA"} if not record["media"] else set())), "media": record["media"]})
    return result


def tables(rows: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    keys = ("mode", "stage", "model", "source_kind", "family", "condition", "arm")
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    result = []
    for key, group in sorted(groups.items()):
        known = [money(row["cost"]["known_usd"]) for row in group]
        liabilities = [money(row["cost"]["unresolved_usd"]) for row in group]
        settled = all(row["cost"]["state"] in {"known", "known_zero"} for row in group)
        successes = sum(row["success"] is True for row in group)
        total = sum(known, Decimal(0)) if settled else None
        positives = lambda name: sum(row["outcome"].get(name) is True for row in group)
        timing = {}
        for name in ("effect", "visible_confirmation"):
            observations = [row["latency"][name] for row in group
                            if row["latency"] and row["latency"][name] is not None]
            reached = [value["latency_ns"] for value in observations if value["attained"]]
            timing[name] = {"applicable_known": len(observations),
                            "attained": len(reached), "scheduled_denominator": len(group),
                            "nonattainment": len(observations)-len(reached),
                            "unknown_or_no_onset": len(group)-len(observations),
                            "reached_only_median_ns": statistics.median(reached) if reached else None,
                            "capped_median_ns": statistics.median(
                                value["capped_ns"] for value in observations) if observations else None,
                            "post_onset_horizon_ns": 180_000_000_000}
        origins = {name: sum(row["outcome"].get("bad_effect_origins", {}).get(name, 0)
                             for row in group)
                   for name in ("agent_direct", "controller_retry", "controller_resolve", "unattributed")}
        result.append({**dict(zip(keys, key)), "scheduled": len(group),
                       "dispatched": sum(row["status"] != "not_executed" for row in group),
                       "valid": sum(row["status"] == "valid" for row in group),
                       "not_executed": sum(row["status"] == "not_executed" for row in group),
                       "harness_unknown": sum(row["status"] == "harness_unknown" for row in group),
                       "success": sum(row["success"] is True for row in group),
                       "success_denominator": len(group), "any_bad": sum(row["harm"] is True for row in group),
                       "duplicate": positives("duplicate_effect"), "wrong": positives("wrong_effect"),
                       "missing": positives("missing_effect"),
                       "overlap": sum(row["outcome"].get("duplicate_effect") is True
                                      and row["outcome"].get("wrong_effect") is True for row in group),
                       "fired": positives("fired"), "not_fired": positives("not_fired"),
                       "terminations": dict(Counter(row["termination"] for row in group)),
                       "incomplete": sum(row["outcome"].get("terminal_status") == "incomplete" for row in group),
                       "timing": timing, "bad_effect_origin_counts": origins,
                       "origin_evidence_unknown_runs": sum(row["status"] == "harness_unknown" for row in group),
                       "actions_known": sum(row["actions"] or 0 for row in group),
                       "actions_unknown_count": sum(row["actions"] is None for row in group),
                       "model_calls_known": sum(row["model_calls"] or 0 for row in group),
                       "model_calls_unknown_count": sum(row["model_calls"] is None for row in group),
                       "attempts_known": sum(row["attempts"] or 0 for row in group),
                       "attempts_unknown_count": sum(row["attempts"] is None for row in group),
                       "known_cost_lower_bound_usd": str(sum((v for v in known if v is not None), Decimal(0)))
                                                    if any(v is not None for v in known) else None,
                       "settled_cost_usd": str(sum(known, Decimal(0))) if settled else None,
                       "cost_per_scheduled_usd": str(total/len(group)) if settled else None,
                       "cost_per_success_usd": str(total/successes) if settled and successes else None,
                       "unresolved_bound_usd": str(sum(liabilities, Decimal(0))) if all(
                           v is not None for v in liabilities) else None,
                       "unknown_cost_count": sum(row["cost"]["state"] in {"unknown", "reserved_unsettled"}
                                                 for row in group),
                       "measurement": "not yet measured" if all(row["status"] == "not_executed" for row in group)
                                      else "source-kind-specific observations; qualification pending"})
    return result
