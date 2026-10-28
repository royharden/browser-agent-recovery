"""Trusted sequential keyless orchestration; backend injected by operator code.

No plugin imports, authority handles or actor code loading. External admission
verification and reset/seal enforcement are producer obligations, not inferred
from a banner. This source has not run or qualified those boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Callable, Protocol

from .freeze import canonical, digest, implementation_pins, load_json, require_pins
from .matrix import validate_matrix
from .metrics import joined_rows
from .oracle import validate_spec
from .report import build_report
from .report_html import media_path


@dataclass(frozen=True)
class RunLease:
    schedule_id: str
    run_id: str
    epoch: str
    clock_id: str
    namespace: str
    context_id: str


@dataclass(frozen=True)
class SealedRun:
    schedule_id: str
    lease: RunLease
    record: dict


@dataclass(frozen=True)
class VerifiedAdmission:
    """Only the trusted external verifier may construct this decision.

    A JSON PASS is not verification. CLI deliberately cannot construct PASS.
    input_sha256 binds matrix, private specs, config, price and report pins.
    """
    state: str
    input_sha256: str
    reasons: tuple[str, ...]


class MatrixRunPort(Protocol):
    offline_only: bool
    clock_id: str

    def now_ns(self) -> int: ...
    def reset(self, row: dict, config: dict) -> RunLease: ...
    def execute(self, lease: RunLease, row: dict, config: dict,
                deadline_ns: int) -> SealedRun: ...
    def close(self, lease: RunLease) -> None: ...


def _copy(value: object):
    return load_json(canonical(value))


def validate_inputs(inputs: dict) -> dict:
    if not isinstance(inputs, dict) or set(inputs) != {
            "matrix", "specs", "config", "price", "pins", "limits", "entrypoint_sha256"}:
        raise ValueError("closed matrix input fields required")
    result = _copy(inputs)
    matrix = validate_matrix(result["matrix"])
    ids = {row["schedule_id"] for row in matrix["schedule"]}
    if not isinstance(result["specs"], dict) or set(result["specs"]) - ids:
        raise ValueError("private specs must be keyed only by scheduled row IDs")
    for spec in result["specs"].values():
        validate_spec(spec)
    entrypoint = Path(__file__).resolve().parents[1] / "scripts" / "keyless_matrix.py"
    if result["entrypoint_sha256"] != hashlib.sha256(entrypoint.read_bytes()).hexdigest():
        raise ValueError("external operator entrypoint byte pin mismatch")
    limits = result["limits"]
    ceilings = {"max_rows": 4000, "max_actions": 40, "max_probes": 40, "max_model_calls": 16,
                "run_timeout_ns": 180_000_000_000,
                "total_timeout_ns": 720_000_000_000_000}
    if not isinstance(limits, dict) or set(limits) != set(ceilings) or any(
            type(limits[key]) is not int or not 1 <= limits[key] <= bound
            for key, bound in ceilings.items()):
        raise ValueError("explicit positive bounded row/action/probe/time limits required")
    config = result["config"]
    if (not isinstance(config, dict) or set(config) != {"bootstrap_seed", "resamples", "horizon_ns"}
            or type(config["bootstrap_seed"]) is not int
            or type(config["resamples"]) is not int or not 1 <= config["resamples"] <= 100_000
            or config["horizon_ns"] != 180_000_000_000 or not isinstance(result["price"], dict)):
        raise ValueError("frozen evaluator config and price mapping required")
    require_pins({**implementation_pins(), "schedule": digest(matrix["schedule"]),
                  "config": digest(config), "price": digest(result["price"])}, result["pins"])
    return result


def _unknown(spec: dict, lease: RunLease | None, reason: str) -> dict:
    # A failed reset may return a typed dataclass with invalid field values.
    # Never let an unvalidated object/NaN contaminate the retained JSON fallback.
    def identity(value: object) -> str | None:
        return value if isinstance(value, str) and value.strip() else None

    return {"seal": None, "spec": spec,
            "execution": {"run_id": identity(lease.run_id) if lease else None,
                          "epoch": identity(lease.epoch) if lease else None,
                          "clock_id": identity(lease.clock_id) if lease else None,
                          "start_ns": None, "termination": "harness_unknown",
                          "actions": None, "model_calls": None, "failures": ["HARNESS_UNKNOWN", reason]},
            "cost": {"state": "unknown", "known_usd": None, "unresolved_usd": None},
            "reads": [], "media": []}


def run_matrix(inputs: dict, *, admission: VerifiedAdmission | None,
               port: MatrixRunPort | None = None,
               stop: Callable[[], bool] = lambda: False) -> dict:
    """Return evaluator-compatible records plus all scheduled lifecycle rows.

    Backend must bound reset/execute/close and enforce deadline on its clock;
    synchronous Python cannot forcibly preempt a dishonest/blocking backend.
    Any lifecycle/clock/identity error stops subsequent dispatch. Raw responses
    remain in the private envelope even when unusable by the evaluator.
    """
    inputs = validate_inputs(inputs)
    matrix, records, lifecycle, raw = inputs["matrix"], {}, [], {}
    schedule, specs, limits = matrix["schedule"], inputs["specs"], inputs["limits"]
    bound = digest(inputs)
    gate = None
    if admission is None or admission.state == "PENDING":
        gate = "admission_pending"
    elif admission.state == "FAIL":
        gate = "admission_fail_skip_all"
    elif admission.state != "PASS" or admission.input_sha256 != bound:
        gate = "admission_unverified_or_input_mismatch"
    elif port is None:
        gate = "single_run_backend_unavailable"
    elif port.offline_only is not True:
        gate = "offline_backend_required"
    used_runs, used_namespaces, used_contexts = set(), set(), set()
    dispatched = 0
    last_now, matrix_deadline = None, None
    deadline_clock_id = port.clock_id if gate is None else None

    def now() -> int:
        nonlocal last_now
        if port.clock_id != deadline_clock_id:
            raise ValueError("backend deadline clock domain changed")
        value = port.now_ns()
        if type(value) is not int or value < 0 or (last_now is not None and value < last_now):
            raise ValueError("invalid/regressing backend deadline clock")
        last_now = value
        return value

    if gate is None:
        try:
            if not isinstance(port.clock_id, str) or not port.clock_id:
                raise ValueError("backend clock identity required")
            matrix_deadline = now() + limits["total_timeout_ns"]
        except Exception:
            gate = "backend_clock_unavailable"
    for scheduled in schedule:
        row_id = scheduled["schedule_id"]
        meta = matrix["metadata"][row_id]
        entry = {"schedule_id": row_id, "status": "not_executed", "reason": gate,
                 "errors": [], "raw_record_retained": False}
        lifecycle.append(entry)
        if gate:
            continue
        if meta["availability"] == "unavailable":
            entry["reason"] = meta["reason"]
            continue
        if row_id not in specs:
            entry["reason"] = "external_private_spec_missing"
            continue
        lease = None
        try:
            if stop():
                gate = "operator_stop"
            elif dispatched >= limits["max_rows"]:
                gate = "matrix_row_cap"
            elif now() >= matrix_deadline:
                gate = "matrix_time_cap"
            if gate:
                entry["reason"] = gate
                continue
            # Private expected specs are deliberately absent from this contract.
            row = {"schedule": _copy(scheduled), "metadata": _copy(meta)}
            config = {**limits, "matrix_input_sha256": bound,
                      "matrix_deadline_ns": matrix_deadline}
            deadline = min(matrix_deadline, now() + limits["run_timeout_ns"])
            config["run_deadline_ns"] = deadline
            # Attempted reset may have effects even if it raises or returns garbage.
            dispatched += 1
            entry["status"] = "harness_unknown"
            records[row_id] = _unknown(specs[row_id], None, "reset_or_execute_failed")
            lease = port.reset(_copy(row), _copy(config))
            if (not isinstance(lease, RunLease) or lease.schedule_id != row_id
                    or lease.clock_id != port.clock_id or any(
                        not isinstance(value, str) or not value for value in (
                            lease.run_id, lease.epoch, lease.namespace, lease.context_id))
                    or lease.run_id in used_runs or lease.namespace in used_namespaces
                    or lease.context_id in used_contexts):
                raise ValueError("fresh reset/namespace/context/row identity required")
            used_runs.add(lease.run_id)
            used_namespaces.add(lease.namespace)
            used_contexts.add(lease.context_id)
            records[row_id] = _unknown(specs[row_id], lease, "execute_failed")
            if stop() or now() >= deadline:
                raise ValueError("stopped or deadline exhausted after reset")
            sealed = port.execute(lease, _copy(row), _copy(config), deadline)
            if not isinstance(sealed, SealedRun):
                raise ValueError("sealed run result required")
            raw[row_id] = _copy(sealed.record)
            entry["raw_record_retained"] = True
            if sealed.schedule_id != row_id or sealed.lease != lease:
                raise ValueError("sealed row/reset identity mismatch")
            record = _copy(sealed.record)
            # Backend cannot replace operator private truth; actor never receives it.
            if set(record) != {"seal", "spec", "execution", "cost", "reads", "media"}:
                raise ValueError("closed evaluator record required")
            record["spec"] = _copy(specs[row_id])
            if not isinstance(record["media"], list):
                raise ValueError("media receipt must be a list")
            for path in record["media"]:
                media_path(path)
            execution = record["execution"]
            if (not isinstance(execution, dict) or not isinstance(execution.get("termination"), str)
                    or not execution["termination"].strip()):
                raise ValueError("nonempty string execution termination required")
            if (execution["run_id"] != lease.run_id or execution["epoch"] != lease.epoch
                    or execution["clock_id"] != lease.clock_id):
                raise ValueError("execution receipt/reset mismatch")
            joined = joined_rows([scheduled], {row_id: record})[0]
            records[row_id] = record
            entry.update(status=joined["status"], reason=execution["termination"])
            if (joined["status"] == "harness_unknown" or now() > deadline
                    or execution["actions"] is None or execution["actions"] > limits["max_actions"]
                    or execution["model_calls"] is None
                    or execution["model_calls"] > limits["max_model_calls"]):
                raise ValueError("evidence/clock/action cap/offline accounting violation")
        except Exception as error:
            gate = "harness_unknown_stop"
            entry.update(status="harness_unknown" if row_id in records else "not_executed",
                         reason=gate)
            entry["errors"].append(type(error).__name__ + ": " + str(error))
            # Preserve every usable attempted record but invalidate its seal when
            # identity/time/cap cannot be trusted; raw sidecar retains original.
            if row_id in records:
                records[row_id] = _unknown(specs[row_id], lease if isinstance(lease, RunLease) else None,
                                           "invalid_run_record: " + str(error))
        finally:
            if isinstance(lease, RunLease):
                try:
                    port.close(lease)
                    if now() > deadline:
                        raise ValueError("cleanup exceeded run deadline")
                except Exception as error:
                    gate = "cleanup_unknown_stop"
                    entry.update(status="harness_unknown", reason=gate)
                    entry["errors"].append(type(error).__name__ + ": " + str(error))
                    records[row_id]["seal"] = None
    report_inputs = {"schedule": schedule, "records": records, "pins": inputs["pins"],
                     "config": inputs["config"], "price": inputs["price"]}
    report_error = None
    try:
        report = build_report(**report_inputs)
    except Exception as error:
        # Preserve an operator-private failure envelope even if an unforeseen
        # evaluator/aggregation defect prevents rendering the report. Never
        # invent report metrics or suppress retained attempted-run records.
        report = None
        report_error = type(error).__name__ + ": " + str(error)
    body = {"schema": "rlab.matrix-result.v1", "matrix": matrix,
            "input_sha256": bound, "lifecycle": lifecycle, "raw_records": raw,
            "admission": {"state": admission.state if admission else "PENDING",
                          "reasons": list(admission.reasons) if admission else ["external verifier absent"]},
            "report": report, "report_error": report_error,
            "unreported_inputs": report_inputs if report_error else None,
            "runtime_qualification": "unverified"}
    return {**body, "sha256": digest(body)}
