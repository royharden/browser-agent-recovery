"""Closed public receipt shapes. No records or independent truth are minted."""
SCHEMA = "rlab.admission.v1"
MANIFEST_FIELDS = frozenset({"author_id", "custodian_id", "verifier_id", "source_sha256",
                             "interface_sha256", "originality", "provenance", "applicability", "archives"})
RECEIPT_KINDS = ("author", "rights", "custody", "qualification", "approval")
RECEIPT_FIELDS = frozenset({"schema", "kind", "signer_id", "manifest_sha256",
                            "state", "signature", "evidence"})
EVIDENCE_FIELDS = {
    "author": frozenset({"independent", "original", "archive_sha256"}),
    "rights": frozenset({"all_sources_approved", "licence_approval_id", "source_ids"}),
    "custody": frozenset({"archive_sha256", "builder_read_denied", "denied_builder_ids", "probe_receipt_sha256"}),
    "qualification": frozenset({"independent", "all_twenty_cells", "applicability_sha256", "interface_sha256"}),
    "approval": frozenset({"approved_signers", "trust_scope", "independence_appointment_id", "licence_approval_id"}),
}
FAMILIES = ("F1", "F2", "F3", "F4", "FH")  # public labels, never family implementations
CONDITIONS = ("clean", "EXPIRED_VIEW", "STALE_ID", "INTERRUPTED_ACTION")
FORBIDDEN_KEYS = frozenset({"answers", "seed_map", "hidden_cases", "hidden_specs", "archive_path",
                            "archive_contents", "source_code", "heldout_data"})


def receipt_schema(kind: str) -> dict:
    """Serializable field schema for an external producer, not a filled receipt."""
    if kind not in RECEIPT_KINDS:
        raise ValueError("unknown receipt kind")
    return {"schema": "rlab.receipt-schema.v1", "receipt_schema": "rlab.receipt.v1",
            "kind": kind, "fields": sorted(RECEIPT_FIELDS),
            "evidence_fields": sorted(EVIDENCE_FIELDS[kind]),
            "states": ["PASS", "PENDING", "FAIL"], "additional_fields": False}
