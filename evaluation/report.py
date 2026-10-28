"""Documented operator facade; report generation never dispatches a task/model."""
from .freeze import digest, implementation_pins, require_pins
from .metrics import joined_rows, tables
from .paired import contrasts
from .report_html import media_path, render
from .schedule import validate_schedule

SCHEMA = "rlab.report.v1"


def build_report(schedule: list[dict], records: dict, *, pins: dict,
                 config: dict, price: dict) -> dict:
    """Consume externally frozen inputs; no independent receipt is manufactured.

    Records include external private specs: reports remain operator-private
    until a separate release/redaction decision. Source code supplies no truth.
    """
    schedule = validate_schedule(schedule)
    if set(config) != {"bootstrap_seed", "resamples", "horizon_ns"}:
        raise ValueError("closed analysis configuration required")
    if (type(config["bootstrap_seed"]) is not int or type(config["resamples"]) is not int
            or not 1 <= config["resamples"] <= 100_000
            or config["horizon_ns"] != 180_000_000_000):
        raise ValueError("invalid frozen bootstrap configuration/post-onset horizon")
    active = {**implementation_pins(), "schedule": digest(schedule),
              "config": digest(config), "price": digest(price)}
    require_pins(active, pins)
    if not isinstance(records, dict) or not isinstance(price, dict):
        raise ValueError("record and price mappings required")
    rows = joined_rows(schedule, records)
    for row in rows:
        if not isinstance(row["media"], list):
            raise ValueError("media list required")
        for path in row["media"]:
            media_path(path)
    inputs = {"schedule": schedule, "records": records, "config": config, "price": price}
    report = {"schema": SCHEMA, "pins": dict(pins), "inputs": inputs,
              "inputs_sha256": digest(inputs), "rows": rows, "tables": tables(rows),
              "contrasts": contrasts(rows, bootstrap_seed=config["bootstrap_seed"],
                                     resamples=config["resamples"]),
              "qualification": {"runtime": "unverified", "independent_oracle": "PENDING - needs Roy",
                                "independent_arithmetic": "PENDING - needs Roy",
                                "admission": "PENDING - needs Roy"}}
    # Detach caller-owned nested objects to keep later caller mutation from
    # silently rewriting this candidate's input/metric binding.
    from .freeze import canonical, load_json
    report = load_json(canonical(report))
    return {**report, "sha256": digest(report)}


def verify_report(report: dict, *, expected_pins: dict, expected_inputs_sha256: str) -> bool:
    """Verify against EXTERNAL frozen anchors, never report-self-asserted pins."""
    require_pins(report["pins"], expected_pins)
    if report["schema"] != SCHEMA or report["inputs_sha256"] != expected_inputs_sha256:
        raise ValueError("external report/input anchor mismatch")
    if digest(report["inputs"]) != expected_inputs_sha256:
        raise ValueError("attempt/event/spec/schedule/input tampering")
    body = {key: value for key, value in report.items() if key != "sha256"}
    if digest(body) != report["sha256"]:
        raise ValueError("report digest mismatch")
    inputs = report["inputs"]
    rebuilt = build_report(inputs["schedule"], inputs["records"], pins=expected_pins,
                           config=inputs["config"], price=inputs["price"])
    if digest(rebuilt) != digest(report):
        raise ValueError("metrics/row/pin recomputation mismatch")
    return True


def report_html(report: dict) -> str:
    return render(report)
