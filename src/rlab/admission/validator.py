"""Fail-closed external admission records. Hash labels alone authenticate nobody."""
from dataclasses import dataclass
import hashlib
import json
import re

from .schemas import (CONDITIONS, EVIDENCE_FIELDS, FAMILIES, FORBIDDEN_KEYS,
                      MANIFEST_FIELDS, RECEIPT_FIELDS, RECEIPT_KINDS, SCHEMA)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _hash(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 256


@dataclass(frozen=True)
class AdmissionDecision:
    state: str
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return {"state": self.state, "reasons": list(self.reasons),
                "scope": "externally anchored record validation; not authentication or OS proof"}


class _Check:
    def __init__(self) -> None:
        self.fail: list[str] = []
        self.pending: list[str] = []

    def fields(self, value: object, expected: set | frozenset, path: str) -> bool:
        """Check shape without suppressing checks on a partial mapping's fields."""
        if value is None:
            self.pending.append(path+": mapping missing")
            return False
        if not isinstance(value, dict):
            self.fail.append(path+": mapping required")
            return False
        extras, missing = set(value)-expected, expected-set(value)
        if extras:
            self.fail.append(path+": unsupported/forbidden fields")
        if missing:
            self.pending.append(path+": missing fields "+",".join(sorted(missing)))
        return True

    def positive(self, value: object, path: str) -> None:
        if value is False:
            self.fail.append(path+": explicit negative evidence")
        elif value is None:
            self.pending.append(path+": positive external evidence missing")
        elif value is not True:
            self.fail.append(path+": positive evidence must be a literal boolean")

    def text(self, value: object, path: str) -> bool:
        if value is None:
            self.pending.append(path+": text/reference missing")
            return False
        if not _text(value):
            self.fail.append(path+": invalid text/reference")
            return False
        return True

    def pin(self, value: object, path: str) -> bool:
        if value is None:
            self.pending.append(path+": digest missing")
            return False
        if not _hash(value):
            self.fail.append(path+": malformed digest")
            return False
        return True

    def literal(self, value: object, expected: str, path: str) -> None:
        if value is None:
            self.pending.append(path+": confirmation missing")
        elif value != expected:
            self.fail.append(path+": unsupported value")

    def bind(self, value: object, expected: object, path: str) -> None:
        # Each side is validated at its definition. An absent counterpart cannot
        # create a mismatch, but it also cannot supply a positive binding.
        if value is None or expected is None:
            self.pending.append(path+": binding evidence missing")
        elif value != expected:
            self.fail.append(path+": mismatch")

    def anchor(self, value: object, key: str, expected: dict) -> None:
        if key not in expected or expected[key] is None:
            self.pending.append(key+": missing external trusted hash anchor")
        elif not _hash(expected[key]):
            self.fail.append(key+": malformed external hash anchor")
        elif value is None:
            self.pending.append(key+": record missing for external anchor")
        elif digest(value) != expected[key]:
            self.fail.append(key+": external hash mismatch")

    def decision(self) -> AdmissionDecision:
        return AdmissionDecision("FAIL" if self.fail else "PENDING" if self.pending else "PASS",
                                 tuple(["FAIL: "+s for s in self.fail]+["PENDING: "+s for s in self.pending]))


def _identities(value: object, check: _Check, name: str) -> frozenset[str]:
    if value is None or value == ():
        check.pending.append(name+": external identities missing")
        return frozenset()
    if not isinstance(value, (set, frozenset, tuple, list)) or any(not _text(v) for v in value):
        check.fail.append(name+": invalid external identity collection")
        return frozenset()
    result = frozenset(value)
    if not result:
        check.pending.append(name+": external identities missing")
    return result


def _forbidden(value: object, depth: int = 0) -> bool:
    if depth > 16:
        return True
    if isinstance(value, dict):
        return any(not isinstance(key, str) or key.casefold() in FORBIDDEN_KEYS
                   or _forbidden(child, depth+1) for key, child in value.items())
    if isinstance(value, list):
        return any(_forbidden(child, depth+1) for child in value)
    return False


def _archives(value: object, check: _Check, path: str) -> dict:
    if not check.fields(value, {"F4", "FH"}, path):
        return {}
    for family in ("F4", "FH"):
        check.pin(value.get(family), path+"."+family)
    return value


def _archive_binding(value: object, expected: dict, check: _Check, path: str) -> None:
    archives = _archives(value, check, path)
    for family in ("F4", "FH"):
        check.bind(archives.get(family), expected.get(family), path+"."+family)


def admit(document: dict | None, *, expected_hashes: dict, builder_ids: object,
          trusted_ids: object = ()) -> AdmissionDecision:
    """Validate only externally anchored records/identities already checked by operator.

    trusted_ids must be explicitly supplied from the operator's verified identity
    and appointment records. Omitting it yields PENDING, never automatic trust.
    Do not construct anchors from this untrusted document merely to get PASS.
    """
    check = _Check()
    if document is None:
        return AdmissionDecision("PENDING", ("PENDING: admission document missing",))
    try:
        if not isinstance(expected_hashes, dict):
            return AdmissionDecision("FAIL", ("FAIL: expected_hashes must be an external mapping",))
        builders = _identities(builder_ids, check, "builder_ids")
        trusted = _identities(trusted_ids, check, "trusted_ids")
        # Reject non-JSON/cyclic/oversized content before walking it. No archive
        # is read; a digest is the only allowed hidden-artifact reference.
        encoded = json.dumps(document, sort_keys=True, allow_nan=False)
        if len(encoded.encode()) > 1_000_000 or _forbidden(document):
            return AdmissionDecision("FAIL", ("FAIL: forbidden/deep/oversized admission content",))
        if not check.fields(document, {"schema", "manifest", "receipts"}, "document"):
            return check.decision()
        check.literal(document.get("schema"), SCHEMA, "document.schema")
        manifest_record, receipts = document.get("manifest"), document.get("receipts")
        manifest = manifest_record if check.fields(manifest_record, MANIFEST_FIELDS, "manifest") else {}
        check.anchor(manifest_record, "manifest", expected_hashes)
        for key in ("author_id", "custodian_id", "verifier_id"):
            identity = manifest.get(key)
            if not check.text(identity, key):
                continue
            if identity in builders:
                check.fail.append(key+": builder cannot supply independent admission")
            elif identity not in trusted:
                check.pending.append(key+": identity/appointment not externally trusted")
        if _text(manifest.get("author_id")) and manifest.get("author_id") == manifest.get("verifier_id"):
            check.fail.append("oracle/admission verifier must not author the data")
        for key in ("source_sha256", "interface_sha256"):
            check.pin(manifest.get(key), key)
            check.pin(expected_hashes.get(key), key+" external pin")
            check.bind(manifest.get(key), expected_hashes.get(key), key+" external pin")
        check.literal(manifest.get("originality"), "original_synthetic_only", "manifest.originality")
        archives = _archives(manifest.get("archives"), check, "manifest.archives")
        provenance = manifest.get("provenance")
        sources = []
        source_approvals = []
        complete_source_ids = isinstance(provenance, list) and bool(provenance)
        if provenance is None:
            check.pending.append("positive provenance/rights missing")
        elif not isinstance(provenance, list):
            check.fail.append("provenance must be a list")
        elif not provenance:
            check.pending.append("positive provenance/rights missing")
        else:
            for source in provenance:
                if not check.fields(source, {"id", "sha256", "source", "original", "rights_approval_id"}, "provenance"):
                    complete_source_ids = False
                    continue
                source_id, origin = source.get("id"), source.get("source")
                if check.text(source_id, "provenance.id"):
                    if source_id in sources:
                        check.fail.append("duplicate provenance source")
                    sources.append(source_id)
                else:
                    complete_source_ids = False
                check.pin(source.get("sha256"), "provenance.sha256")
                if check.text(origin, "provenance.source"):
                    if not origin.startswith("original:") or not _text(origin[len("original:"):]):
                        check.fail.append("source must identify original synthetic material, no external task URL")
                    elif _text(source_id):
                        check.bind(origin, "original:"+source_id, "original synthetic source")
                check.positive(source.get("original"), "original provenance")
                approval = source.get("rights_approval_id")
                if check.text(approval, "provenance.rights_approval_id"):
                    source_approvals.append(approval)
        cells = manifest.get("applicability")
        seen = set()
        if cells is None:
            check.pending.append("positive applicability missing")
        elif not isinstance(cells, list):
            check.fail.append("applicability must be a list")
        else:
            for cell in cells:
                if not check.fields(cell, {"family", "condition", "applicable", "semantics_sha256"}, "applicability"):
                    continue
                family, condition = cell.get("family"), cell.get("condition")
                for name, value, allowed in (("family", family, FAMILIES), ("condition", condition, CONDITIONS)):
                    if value is None:
                        check.pending.append("applicability."+name+": label missing")
                    elif not isinstance(value, str) or value not in allowed:
                        check.fail.append("unknown family-condition cell: "+name)
                if isinstance(family, str) and family in FAMILIES and isinstance(condition, str) and condition in CONDITIONS:
                    key = (family, condition)
                    if key in seen:
                        check.fail.append("duplicate family-condition cell")
                    seen.add(key)
                check.positive(cell.get("applicable"), "semantic applicability")
                check.pin(cell.get("semantics_sha256"), "cell semantic pin")
            if seen != {(family, condition) for family in FAMILIES for condition in CONDITIONS}:
                check.pending.append("all20 positive applicability cells required; no N/A substitution")
        if receipts is None:
            check.pending.append("receipts missing")
            receipts = {}
        elif not isinstance(receipts, dict):
            check.fail.append("receipts must be a mapping")
            receipts = {}
        if set(receipts)-set(RECEIPT_KINDS):
            check.fail.append("unsupported receipt kinds")
        records = {}
        evidence_records = {}
        for kind in RECEIPT_KINDS:
            receipt = receipts.get(kind)
            check.anchor(receipt, kind, expected_hashes)
            if receipt is None:
                check.pending.append(kind+": receipt missing")
                continue
            if not check.fields(receipt, RECEIPT_FIELDS, kind):
                continue
            records[kind] = receipt
            check.literal(receipt.get("schema"), "rlab.receipt.v1", kind+".schema")
            check.literal(receipt.get("kind"), kind, kind+".kind")
            state = receipt.get("state")
            if state == "FAIL":
                check.fail.append(kind+": explicit qualification failure")
            elif state == "PENDING" or state is None:
                check.pending.append(kind+": receipt not positively accepted")
            elif state != "PASS":
                check.fail.append(kind+": invalid receipt state")
            check.text(receipt.get("signature"), kind+".signature")
            signer = receipt.get("signer_id")
            if check.text(signer, kind+".signer_id"):
                if signer in builders:
                    check.fail.append(kind+": builder cannot sign independent gate")
                elif signer not in trusted:
                    check.pending.append(kind+": signer not externally verified")
            check.pin(receipt.get("manifest_sha256"), kind+".manifest_sha256")
            check.bind(receipt.get("manifest_sha256"),
                       digest(manifest_record) if isinstance(manifest_record, dict) else None,
                       kind+" manifest pin")
            evidence = receipt.get("evidence")
            if check.fields(evidence, EVIDENCE_FIELDS[kind], kind+".evidence"):
                evidence_records[kind] = evidence
        roles = {"author": "author_id", "custody": "custodian_id", "qualification": "verifier_id"}
        for kind, identity in roles.items():
            if kind in records:
                check.bind(records[kind].get("signer_id"), manifest.get(identity), kind+" role identity")
        if "author" in evidence_records:
            evidence = evidence_records["author"]
            check.positive(evidence.get("independent"), "author independence")
            check.positive(evidence.get("original"), "author originality")
            _archive_binding(evidence.get("archive_sha256"), archives, check, "author archive pin")
        rights_approval = None
        if "rights" in evidence_records:
            evidence = evidence_records["rights"]
            check.positive(evidence.get("all_sources_approved"), "all source rights")
            rights_approval = evidence.get("licence_approval_id")
            check.text(rights_approval, "rights.licence_approval_id")
            source_ids = evidence.get("source_ids")
            if source_ids is None:
                check.pending.append("rights source coverage missing")
            elif not isinstance(source_ids, list) or any(not _text(item) for item in source_ids):
                check.fail.append("invalid rights source IDs")
            elif len(source_ids) != len(set(source_ids)):
                check.fail.append("duplicate rights source IDs")
            elif complete_source_ids:
                if sorted(source_ids) != sorted(sources):
                    check.fail.append("rights source coverage mismatch")
            else:
                check.pending.append("rights source coverage lacks complete provenance IDs")
        for approval in source_approvals:
            check.bind(approval, rights_approval, "provenance/rights licence approval")
        if "custody" in evidence_records:
            evidence = evidence_records["custody"]
            check.positive(evidence.get("builder_read_denied"), "actual builder read denial")
            denied = _identities(evidence.get("denied_builder_ids"), check, "denied_builder_ids")
            if not builders <= denied:
                check.pending.append("custody denial does not cover every external builder identity")
            _archive_binding(evidence.get("archive_sha256"), archives, check, "custody archive pin")
            probe = expected_hashes.get("custody_probe")
            check.pin(probe, "external custody denial probe")
            check.pin(evidence.get("probe_receipt_sha256"), "custody denial probe")
            check.bind(evidence.get("probe_receipt_sha256"), probe, "custody denial probe hash")
        if "qualification" in evidence_records:
            evidence = evidence_records["qualification"]
            check.positive(evidence.get("independent"), "qualification independence")
            check.positive(evidence.get("all_twenty_cells"), "twenty-cell qualification")
            check.pin(evidence.get("applicability_sha256"), "qualification.applicability_sha256")
            check.pin(evidence.get("interface_sha256"), "qualification.interface_sha256")
            check.bind(evidence.get("applicability_sha256"), digest(cells) if isinstance(cells, list) else None,
                       "qualification applicability pin")
            check.bind(evidence.get("interface_sha256"), manifest.get("interface_sha256"),
                       "qualification interface pin")
        if "approval" in evidence_records:
            evidence = evidence_records["approval"]
            trust_scope = evidence.get("trust_scope")
            if check.text(trust_scope, "approval.trust_scope") and trust_scope != "verified_external_records":
                check.pending.append("operator has not verified external signatures/identity/receipts")
            check.text(evidence.get("independence_appointment_id"), "approval.independence_appointment_id")
            check.text(evidence.get("licence_approval_id"), "approval.licence_approval_id")
            approved_signers = evidence.get("approved_signers")
            if check.fields(approved_signers, set(RECEIPT_KINDS)-{"approval"}, "approved_signers"):
                for kind in RECEIPT_KINDS[:-1]:
                    approved = approved_signers.get(kind)
                    check.text(approved, "approved_signers."+kind)
                    check.bind(approved, records.get(kind, {}).get("signer_id"),
                               "operator approved signer: "+kind)
            check.bind(evidence.get("licence_approval_id"), rights_approval, "operator/rights licence approval")
        return check.decision()
    except (TypeError, ValueError, KeyError, RecursionError) as error:
        check.fail.append("malformed/corrupt admission record: "+str(error))
        return check.decision()
