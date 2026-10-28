"""Authority-clock attainment; a post-onset horizon is not the task deadline."""
from .oracle import assess, integer, state_at, validate_seal, validate_spec

HORIZON_NS = 180_000_000_000


def latency(seal: dict, spec: dict, reads: list[dict], start_ns: int | None) -> dict:
    unknown = {"effect": None, "visible_confirmation": None,
               "horizon_ns": HORIZON_NS, "duration_ns": None,
               "reason": "invalid or incomplete authority timing"}
    try:
        checked = validate_seal(seal)
        validate_spec(spec)
        bundle, effects = checked["bundle"], checked["effects"]
        run, fault, terminal = bundle["run"], bundle["fault"], bundle["terminal"]
        if start_ns is not None:
            integer(start_ns, "execution.start_ns")
            if start_ns > terminal["ns"] or (effects and start_ns > effects[0]["ns"]):
                raise ValueError("task start is after authority activity")
        result = {**unknown, "duration_ns": None if start_ns is None else terminal["ns"]-start_ns}
        if checked["timing_unknown"] or fault["harness_error"]:
            return result
        if fault["kind"] == "clean" or fault["disposition"] != "fired":
            return {**result, "reason": "no injected onset; latency not applicable"}
        onset = fault["onset_ns"]
        if start_ns is not None and onset < start_ns:
            raise ValueError("onset predates task")
        attainment = None
        for count in range(len(effects)+1):
            prefix = effects[:count]
            stamp = onset if count == 0 else max(onset, prefix[-1]["ns"])
            # State already correct at onset yields zero; evaluate all mutations
            # at/before onset together, never an earlier compensated-away state.
            if count < len(effects) and effects[count]["ns"] <= onset:
                continue
            if assess(spec, prefix, state_at(spec, prefix))["success"]:
                attainment = stamp-onset
                break
        effect_attained = attainment is not None and attainment <= HORIZON_NS
        effect = {"attained": effect_attained,
                  "latency_ns": attainment if effect_attained else None,
                  "capped_ns": attainment if effect_attained else HORIZON_NS}
        visible = None
        seen = set()
        final_ok = assess(spec, effects, state_at(spec, effects))["success"]
        for read in reads:
            if not isinstance(read, dict):
                raise ValueError("invalid history receipt")
            required = {"run_id", "epoch", "clock_id", "request_id", "started_ns", "completed_ns",
                        "served_version", "latest_version", "successful", "complete", "unfiltered",
                        "cached", "aliases"}
            if not required <= set(read):
                raise ValueError("history timing/completeness metadata missing")
            started = integer(read["started_ns"], "read.started_ns")
            completed = integer(read["completed_ns"], "read.completed_ns")
            if (read["run_id"] != run["run"] or read["epoch"] != run["epoch"]
                    or read["clock_id"] != run["clock"] or completed < started
                    or completed > terminal["ns"]):
                raise ValueError("read clock/run/timing mismatch")
            served = integer(read["served_version"], "read.served_version")
            latest = integer(read["latest_version"], "read.latest_version")
            if not served <= latest <= run["version"]:
                raise ValueError("read watermark outside sealed transition prefix")
            if latest and bundle["visibility"][latest-1]["committed_ns"] > started:
                raise ValueError("history snapshot claims a transition before it committed")
            if not isinstance(read["request_id"], str):
                raise ValueError("invalid history request identity")
            fresh = bool(read["request_id"]) and read["request_id"] not in seen
            seen.add(read["request_id"])
            complete = (read["successful"] is True and read["complete"] is True
                        and read["unfiltered"] is True and read["cached"] is False
                        and read["aliases"] is False)
            if (final_ok and fresh and complete and started >= onset
                    and served == latest == run["version"]):
                candidate = completed-onset
                visible = candidate if visible is None else min(visible, candidate)
        confirmation_attained = visible is not None and visible <= HORIZON_NS
        confirmation = {"attained": confirmation_attained,
                        "latency_ns": visible if confirmation_attained else None,
                        "capped_ns": visible if confirmation_attained else HORIZON_NS,
                        "note": "counted-read opportunity differs by arm"}
        return {**result, "effect": effect, "visible_confirmation": confirmation, "reason": None}
    except (ValueError, TypeError, KeyError, IndexError):
        return unknown
