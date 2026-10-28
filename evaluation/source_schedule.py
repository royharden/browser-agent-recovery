"""Fixed operator source-schedule binding, never research or data approval.

No writes, task execution or callback/plugin selection. Source/entrypoint bytes
are read only when a later authorized operator calls the fixed build function.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Literal

from .freeze import canonical, digest, load_json
from .matrix_runner import VerifiedAdmission, validate_inputs

MAX_BYTES = 32 * 1024 * 1024
MAX_NODES = 500_000
HASH_KEYS = {"matrix", "schedule", "metadata", "specs", "config", "limits",
             "price", "pins", "source", "oracle", "entrypoint", "admission"}
SCHEMA = "rlab.source-schedule.v1"


@dataclass(frozen=True)
class SourceScheduleArtifact:
    """Immutable DTO: decoding the artifact always returns a fresh JSON tree."""
    state: Literal["ready", "pending", "refused"]
    reasons: tuple[str, ...]
    artifact_json: str | None = None

    @property
    def artifact(self) -> dict | None:
        return None if self.artifact_json is None else load_json(self.artifact_json)

    def to_dict(self) -> dict:
        return {"state": self.state, "reasons": list(self.reasons), "artifact": self.artifact}


def _sha(value: object) -> bool:
    return type(value) is str and len(value) == 64 and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _bounded_copy(value: object):
    """Strict native JSON only; bound traversal before canonical serialization."""
    nodes, size = 0, 0
    active: set[int] = set()

    def charge(amount: int) -> None:
        nonlocal size
        size += amount
        if size > MAX_BYTES:
            raise ValueError("source schedule JSON byte limit")

    def walk(item: object, depth: int = 0):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES or depth > 32:
            raise ValueError("source schedule JSON node/depth limit")
        kind = type(item)
        if item is None or kind is bool:
            charge(5)
            return item
        if kind is int:
            if item.bit_length() > 128:
                raise ValueError("source schedule JSON integer limit")
            charge(len(str(item)))
            return item
        if kind is float:
            if not math.isfinite(item):
                raise ValueError("source schedule nonfinite JSON")
            charge(32)
            return item
        if kind is str:
            if len(item) > 1024 * 1024:
                raise ValueError("source schedule JSON string limit")
            charge(len(canonical(item)))
            return item
        if kind not in (dict, list) or id(item) in active:
            raise ValueError("source schedule requires native acyclic JSON")
        active.add(id(item))
        charge(2)
        try:
            if kind is list:
                result = []
                for child in item:
                    charge(1)
                    result.append(walk(child, depth+1))
                return result
            result = {}
            for key, child in dict.items(item):
                if type(key) is not str or len(key) > 4096:
                    raise ValueError("source schedule JSON key limit/type")
                charge(len(canonical(key))+2)
                result[key] = walk(child, depth+1)
            return result
        finally:
            active.remove(id(item))

    return walk(value)


def _admission_payload(admission: VerifiedAdmission) -> dict:
    if (type(admission) is not VerifiedAdmission or type(admission.state) is not str
            or admission.state not in {"PASS", "PENDING", "FAIL"}
            or not _sha(admission.input_sha256) or type(admission.reasons) is not tuple
            or len(admission.reasons) > 128 or any(
                type(reason) is not str or len(reason) > 1024 for reason in admission.reasons)):
        raise ValueError("bounded external verified admission binding required")
    return {"state": admission.state, "input_sha256": admission.input_sha256,
            "reasons": list(admission.reasons)}


def build_source_schedule(inputs: dict, *, admission: VerifiedAdmission | None,
                          expected_input_sha256: str | None,
                          expected_hashes: dict | None) -> SourceScheduleArtifact:
    """Bind genuine external inputs to actual current source, without execution.

    A typed PASS must already result from external verification; this function
    creates no admission/signature/custody/instrument/research receipt. Hash
    anchors must be externally selected, not generated from untrusted inputs
    merely to obtain ready. Missing positive anchors return no artifact.
    """
    if admission is None:
        return SourceScheduleArtifact("pending", ("external admission binding absent",))
    try:
        admitted = _admission_payload(admission)
    except ValueError:
        return SourceScheduleArtifact("refused", ("invalid external admission binding",))
    if admitted["state"] == "FAIL":
        return SourceScheduleArtifact("refused", ("admission FAIL: no source artifact",))
    if admitted["state"] != "PASS":
        return SourceScheduleArtifact("pending", ("external admission not PASS",))
    if expected_input_sha256 is None or expected_hashes is None:
        return SourceScheduleArtifact("pending", ("external full-input/hash anchors absent",))
    if not _sha(expected_input_sha256) or type(expected_hashes) is not dict:
        return SourceScheduleArtifact("refused", ("malformed external anchors",))
    if (len(expected_hashes) > len(HASH_KEYS)
            or any(type(key) is not str or key not in HASH_KEYS for key in expected_hashes)
            or any(not _sha(value) for value in expected_hashes.values())):
        return SourceScheduleArtifact("refused", ("unknown/malformed source hash anchor",))
    # Detach and bound anchors too; no mutable reference to caller survives.
    expected_hashes = dict(expected_hashes)
    try:
        inputs = _bounded_copy(inputs)
        actual_input = digest(inputs)
        if actual_input != expected_input_sha256 or admitted["input_sha256"] != actual_input:
            return SourceScheduleArtifact("refused", ("external full-input/admission mismatch",))
        # Existing validation regenerates exact original development metadata,
        # validates private specs, and reads actual source/entrypoint byte pins.
        checked = validate_inputs(inputs)
        matrix, pins = checked["matrix"], checked["pins"]
        hashes = {"matrix": digest(matrix), "schedule": pins["schedule"],
                  "metadata": digest(matrix["metadata"]), "specs": digest(checked["specs"]),
                  "config": digest(checked["config"]), "limits": digest(checked["limits"]),
                  "price": digest(checked["price"]), "pins": digest(pins),
                  "source": pins["source"], "oracle": pins["oracle"],
                  "entrypoint": checked["entrypoint_sha256"], "admission": digest(admitted)}
        if any(hashes[key] != value for key, value in expected_hashes.items()):
            return SourceScheduleArtifact("refused", ("external component hash mismatch",))
        if set(expected_hashes) != HASH_KEYS:
            return SourceScheduleArtifact("pending", ("external component hash anchors incomplete",))
        body = {"schema": SCHEMA, "kind": "source_schedule_only", "matrix": matrix,
                "input_sha256": actual_input, "hashes": hashes,
                "qualification": {"runtime": "unverified", "research_freeze": "NOT PROVIDED",
                                  "signature": "NOT PROVIDED", "data_admission_receipt": "NOT PROVIDED",
                                  "instrument_acceptance": "NOT PROVIDED"}}
        artifact = _bounded_copy({**body, "sha256": digest(body)})
        return SourceScheduleArtifact("ready", ("source schedule binding only; no research approval",),
                                      canonical(artifact))
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        return SourceScheduleArtifact("refused", ("invalid source inputs, bounds or current checkout pins",))


def verify_source_schedule(artifact: dict, *, inputs: dict,
                           admission: VerifiedAdmission | None,
                           expected_artifact_sha256: str,
                           expected_input_sha256: str,
                           expected_hashes: dict) -> bool:
    """Verify external digest AND rebuild against original inputs/current bytes.

    This performs source binding only. It never executes tasks, checks billing,
    authenticates a human signer or issues independent qualification.
    """
    if not _sha(expected_artifact_sha256):
        raise ValueError("external source artifact SHA256 anchor required")
    artifact = _bounded_copy(artifact)
    if type(artifact) is not dict or artifact.get("schema") != SCHEMA:
        raise ValueError("source schedule artifact schema required")
    body = {key: value for key, value in artifact.items() if key != "sha256"}
    if (artifact.get("sha256") != expected_artifact_sha256
            or digest(body) != expected_artifact_sha256):
        raise ValueError("external source artifact anchor mismatch")
    rebuilt = build_source_schedule(inputs, admission=admission,
                                    expected_input_sha256=expected_input_sha256,
                                    expected_hashes=expected_hashes)
    if rebuilt.state != "ready" or canonical(rebuilt.artifact) != canonical(artifact):
        raise ValueError("source schedule inputs/current checkout recomputation mismatch")
    return True
