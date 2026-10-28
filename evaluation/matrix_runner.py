"""Trusted sequential keyless orchestration; backend injected by operator code.

No plugin imports, authority handles or actor code loading. External admission
verification and reset/seal enforcement are producer obligations, not inferred
from a banner. This source has not run or qualified those boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
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
    provenance: dict | None = None


@dataclass(frozen=True)
class UnattemptedRun:
    """Trusted preflight refusal before authority/reset/actor/provider activity."""
    schedule_id: str
    reason: str


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
    def preflight(self, row: dict, config: dict) -> UnattemptedRun | None: ...
    def reset(self, row: dict, config: dict) -> RunLease: ...
    def execute(self, lease: RunLease, row: dict, config: dict,
                deadline_ns: int) -> SealedRun: ...
    def close(self, lease: RunLease) -> None: ...


def _copy(value: object):
    return load_json(canonical(value))


MAX_PROVENANCE_BYTES = 2 * 1024 * 1024
MAX_MATRIX_PROVENANCE_BYTES = 64 * 1024 * 1024
MAX_PROVENANCE_NODES = 8192
ATTEMPT_FIELDS = {"request", "binding", "current_cost", "source_cost", "raw_usage",
                  "rejected_response", "error", "timings"}


def capture_provenance(value: object, *, source_kind: str, remaining_bytes: int) -> dict:
    """Detach bounded native JSON without invoking producer repr/serializers.

    Rejected content has a bounded partial representation, explicit errors and
    digest of THAT retained representation, never a claimed hash of lost bytes.
    No object hook, dataclass conversion, repr or plugin method is called.
    """
    errors: list[str] = []
    active: set[int] = set()
    nodes, encoded_bytes = 0, 0

    def reject(reason: str) -> dict:
        if reason not in errors and len(errors) < 24:
            errors.append(reason)
        return {"rejected": reason}

    def walk(item: object, depth: int = 0):
        nonlocal nodes, encoded_bytes
        nodes += 1
        if nodes > MAX_PROVENANCE_NODES:
            return reject("node_limit")
        if depth > 24:
            return reject("depth_limit")
        if encoded_bytes >= min(MAX_PROVENANCE_BYTES, remaining_bytes):
            return reject("byte_limit")
        kind = type(item)
        if item is None or kind is bool:
            encoded_bytes += 5
            return item
        if kind is int:
            if item.bit_length() > 128:
                return reject("integer_limit")
            encoded_bytes += len(str(item))
            return item
        if kind is float:
            if not math.isfinite(item):
                return reject("nonfinite_number")
            encoded_bytes += 32
            return item
        if kind is str:
            if len(item) > 131072:
                marker = reject("string_limit")
                return {**marker, "prefix": item[:1024], "original_characters": len(item)}
            encoded_bytes += len(canonical(item))
            return item
        if kind not in (dict, list):
            return reject("non_json_type")
        if id(item) in active:
            return reject("cycle")
        active.add(id(item))
        try:
            encoded_bytes += 2
            if kind is list:
                result = []
                for index, child in enumerate(item):
                    if index >= 2048 or nodes >= MAX_PROVENANCE_NODES or encoded_bytes >= min(
                            MAX_PROVENANCE_BYTES, remaining_bytes):
                        result.append({**reject("container_limit"), "omitted_items": len(item)-index})
                        break
                    result.append(walk(child, depth+1))
                    encoded_bytes += 1
                return result
            result = {}
            for index, (key, child) in enumerate(dict.items(item)):
                if index >= 2048 or nodes >= MAX_PROVENANCE_NODES or encoded_bytes >= min(
                        MAX_PROVENANCE_BYTES, remaining_bytes):
                    reject("container_limit")
                    break
                if type(key) is not str or len(key) > 4096:
                    reject("invalid_object_key")
                    continue
                encoded_bytes += len(canonical(key))+2
                result[key] = walk(child, depth+1)
            return result
        finally:
            active.remove(id(item))

    if remaining_bytes < 4096:
        retained = reject("matrix_provenance_limit")
    else:
        retained = walk(value)
    state = "rejected" if errors else "unknown"
    if not errors:
        if value is None:
            errors.append("provider_provenance_missing")
        elif type(retained) is not dict or set(retained) != {
                "schema", "source_kind", "state", "provider_attempts", "loop", "reason"}:
            errors.append("closed_provenance_fields_required")
        elif (retained["schema"] != "rlab.run-provenance.v1"
              or retained["source_kind"] != source_kind):
            errors.append("provenance_schema_or_source_mismatch")
        else:
            declared, attempts, loop, reason = (retained[key] for key in (
                "state", "provider_attempts", "loop", "reason"))
            if declared not in ("recorded", "unknown", "not_applicable"):
                errors.append("invalid_provenance_state")
            elif reason is not None and type(reason) is not str:
                errors.append("invalid_provenance_reason")
            elif attempts is not None and (type(attempts) is not list or len(attempts) > 64 or any(
                    type(attempt) is not dict or not ATTEMPT_FIELDS <= set(attempt) for attempt in attempts)):
                errors.append("actual_attempt_fields_required")
            elif loop is not None and type(loop) is not dict:
                errors.append("loop_receipt_mapping_required")
            elif declared == "recorded" and (type(attempts) is not list or type(loop) is not dict):
                errors.append("recorded_attempts_and_loop_required")
            elif declared == "not_applicable" and (
                    source_kind != "scripted" or attempts != [] or loop is not None or not reason):
                errors.append("explicit_scripted_no_provider_declaration_required")
            elif declared == "unknown" and not reason:
                errors.append("unknown_provenance_reason_required")
            else:
                state = declared
    if errors and state != "unknown":
        state = "rejected"
    elif errors and value is not None:
        state = "rejected"
    result = {"state": state, "source_kind": source_kind, "value": retained,
              "errors": errors, "retained_sha256": digest(retained)}
    maximum = min(MAX_PROVENANCE_BYTES, max(4096, remaining_bytes))
    text = canonical(result)
    if len(text) > maximum:
        retained = {"rejected": "encoded_byte_limit", "json_prefix": text[:1024],
                    "partial_representation_sha256": digest(retained)}
        result = {"state": "rejected", "source_kind": source_kind, "value": retained,
                  "errors": ["encoded_byte_limit"], "retained_sha256": digest(retained)}
    return result


def verify_matrix_envelope(result: dict, *, expected_envelope_sha256: str,
                           expected_provenance_sha256: str) -> bool:
    """Check EXTERNALLY retained anchors, not self-selected hashes in a result.

    This does not recompute evaluator metrics or verify billing/human custody.
    Use verify_report separately with its own external report/input anchors.
    Operator must load bounded JSON and independently select both anchors.
    """
    if any(type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
           for value in (expected_envelope_sha256, expected_provenance_sha256)):
        raise ValueError("external envelope/provenance SHA256 anchors required")
    if type(result) is not dict or result.get("schema") != "rlab.matrix-result.v2":
        raise ValueError("matrix result v2 required")
    if (result.get("provenance_sha256") != expected_provenance_sha256
            or digest(result["provenance"]) != expected_provenance_sha256):
        raise ValueError("external provenance anchor mismatch")
    body = {key: value for key, value in result.items() if key != "sha256"}
    if (result.get("sha256") != expected_envelope_sha256
            or digest(body) != expected_envelope_sha256):
        raise ValueError("external result envelope anchor mismatch")
    return True


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
    provenance, provenance_bytes = {}, 0
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
        provenance[row_id] = {"state": "not_executed", "value": None}
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
            # D1 checks D2's externally cleared prompt/profile readiness without
            # running/resetting authority, actor, observation or provider. Only
            # this pre-attempt path can leave a refused row not_executed.
            readiness = port.preflight(_copy(row), _copy(config))
            if isinstance(readiness, UnattemptedRun):
                if (readiness.schedule_id != row_id or not isinstance(readiness.reason, str)
                        or not readiness.reason.strip()):
                    raise ValueError("bound preflight refusal identity/reason required")
                entry["reason"] = readiness.reason
                continue
            if readiness is not None:
                raise ValueError("typed preflight refusal or None required")
            if stop() or now() >= matrix_deadline:
                gate = "operator_stop_or_matrix_deadline"
                entry["reason"] = gate
                continue
            deadline = min(matrix_deadline, now() + limits["run_timeout_ns"])
            config["run_deadline_ns"] = deadline
            # Attempted reset may have effects even if it raises or returns garbage.
            dispatched += 1
            entry["status"] = "harness_unknown"
            records[row_id] = _unknown(specs[row_id], None, "reset_or_execute_failed")
            provenance[row_id] = {"state": "unknown", "value": None,
                                  "errors": ["no_returned_attempt_provenance"]}
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
            # Capture BEFORE record/identity/media/oracle processing. Rejection
            # must not destroy actual provider/source-cost/usage evidence.
            provenance[row_id] = capture_provenance(
                sealed.provenance, source_kind=scheduled["source_kind"],
                remaining_bytes=MAX_MATRIX_PROVENANCE_BYTES-provenance_bytes)
            provenance_bytes += len(canonical(provenance[row_id]))
            raw[row_id] = _copy(sealed.record)
            entry["raw_record_retained"] = True
            if provenance[row_id]["state"] not in {"recorded", "not_applicable"}:
                raise ValueError("provider provenance missing/unknown/rejected; retained privately")
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
    body = {"schema": "rlab.matrix-result.v2", "matrix": matrix,
            "input_sha256": bound, "lifecycle": lifecycle, "raw_records": raw,
            "provenance": provenance, "provenance_sha256": digest(provenance),
            "admission": {"state": admission.state if admission else "PENDING",
                          "reasons": list(admission.reasons) if admission else ["external verifier absent"]},
            "report": report, "report_error": report_error,
            "unreported_inputs": report_inputs if report_error else None,
            "runtime_qualification": "unverified"}
    return {**body, "sha256": digest(body)}
