"""Stable failure labels; unknown evidence is never a clean negative."""


def labels(outcome: dict, execution: dict, *, not_executed: bool = False) -> list[str]:
    result = set(execution.get("failures", []))
    if any(not isinstance(label, str) for label in result):
        raise ValueError("failure labels must be strings")
    if not_executed:
        result.add("NOT_EXECUTED")
    if outcome.get("status") == "harness_unknown":
        result.add("HARNESS_UNKNOWN")
    if outcome.get("duplicate_effect"):
        result.add("DUPLICATE_EFFECT")
    if outcome.get("wrong_effect"):
        result.add("WRONG_EFFECT")
    if outcome.get("missing_effect"):
        result.add("MISSING_EFFECT")
    if outcome.get("not_fired"):
        result.add("NOT_FIRED")
    if outcome.get("timing_unknown"):
        result.add("CLOCK_DOMAIN")
    return sorted(result)
