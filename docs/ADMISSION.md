# External admission record validation

Source construction only. No independent appointment, signature, archive, probe,
licence, applicability record or acceptance receipt is created by this package.
No hidden archive is opened. Runtime and independent qualification remain pending.

Facade: `from rlab.admission import admit, AdmissionDecision, receipt_schema`.
`admit(document, *, expected_hashes, builder_ids, trusted_ids=())` returns a frozen
decision with `state` PASS/PENDING/FAIL, tuple `reasons`, and `.to_dict()` for CLI
serialization. The additional optional trusted_ids argument is intentional:
without externally verified author/role/operator identities, admission is PENDING.
Builder IDs and hashes alone are not a trust appointment. D1's CLI must preserve
this default rather than deriving trusted identities from the document.

PASS means the supplied shapes/positive records agree with all explicitly supplied
EXTERNAL trusted anchors. It does not authenticate a signer or perform an OS
read-denial probe. The operator must retain independently verified source records,
appointments/signatures and actual custody evidence, then supply their hashes and
trusted identity IDs. Never calculate trust anchors from an untrusted document just
to make it pass. Dirty construction does not supply any of these inputs.

FAIL means explicit negative, mismatch, malformed/forbidden data or corruption;
skip M18 execution, including keyless execution. Missing positive evidence or trust
is PENDING and also blocks qualification. No N/A or reduced-family fallback turns
FAIL into keyless PASS. No delegated stand-in substitutes for the independent roles.

## Closed JSON shapes

Top level: exactly schema=`rlab.admission.v1`, manifest, receipts.
Manifest fields: author_id, custodian_id, verifier_id, source_sha256,
interface_sha256, originality, provenance, applicability, archives.
Originality must be `original_synthetic_only`. All three role IDs must be external
trusted identities and outside builder_ids; verifier must differ from data author.
Author and custodian may be the same independently appointed actor. Operator/rights
signers are separately verified; this package invents no identity or signature system.

Provenance is a nonempty list of closed objects id, sha256, source, original,
rights_approval_id. Source must equal `original:<id>` and original must be true:
external task datasets, URLs and task copies are forbidden. Every source's
rights_approval_id must equal the supplied rights receipt evidence's
licence_approval_id, which must also equal the operator approval's
licence_approval_id. These IDs reference the same externally approved rights
record; nonempty unrelated references do not qualify. They are not licence
choices made by the builder, and matching strings do not authenticate the record.
Applicability is exactly one positive cell for every public family label
F1/F2/F3/F4/FH crossed with clean/EXPIRED_VIEW/STALE_ID/INTERRUPTED_ACTION.
Each cell has family, condition, applicable, semantics_sha256. These labels and
semantic digests contain no implementations, hidden variants, answers or seeds.
Archives has exactly F4 and FH, each a lowercase SHA256 digest only.

Receipts is a mapping keyed author, rights, custody, qualification, approval.
Every receipt has exactly schema=`rlab.receipt.v1`, kind, signer_id,
manifest_sha256, state, signature, evidence. State is PASS/PENDING/FAIL. Signature
is a reference/representation of the operator-verified external signature, never
proof merely because a string is nonempty. All receipts bind the same canonical
manifest SHA256. `receipt_schema(kind)` returns a serializable field schema only,
not a filled receipt or acceptance.

Evidence fields, with no additional fields:

| Kind | Evidence |
| --- | --- |
| author | independent, original, archive_sha256 (same F4/FH mapping) |
| rights | all_sources_approved, licence_approval_id, source_ids (complete provenance IDs) |
| custody | archive_sha256, builder_read_denied, denied_builder_ids, probe_receipt_sha256 |
| qualification | independent, all_twenty_cells, applicability_sha256, interface_sha256 |
| approval | approved_signers (author/rights/custody/qualification IDs), trust_scope=`verified_external_records`, independence_appointment_id, licence_approval_id |

Custody must cover every external builder ID and reference the same archive pins
and independently retained denial-probe hash. Actual OS denial is required later;
a boolean claim is not a probe. Qualification signer is the manifest verifier;
author/custody signers match their manifest roles. Operator approval names the
same signers and licence approval. Unknown approval trust stays PENDING.

External expected_hashes keys: manifest (canonical JSON hash), author, rights,
custody, qualification, approval (canonical full receipt hashes), custody_probe
(actual external probe receipt hash), source_sha256, interface_sha256 (direct
expected pins). Hashes are lowercase SHA256. `rlab.admission.digest(value)` exposes
the canonical algorithm for an independently controlled receipt preparation tool;
it is not authorization to mint or self-approve evidence.

Missing whole document is PENDING. Missing or null fields/evidence/signatures/
licence/positive rights/custody/appointments/anchors remain PENDING. Each partial
object still has every supplied field checked: missing schema, manifest, source,
cell, receipt or evidence fields never suppress a present negative or invalid
value. Positive claims require literal JSON true; literal false and supplied
nonboolean values (including strings and integers) are FAIL. Supplied malformed
identities, signatures and approval references are FAIL, including empty strings;
only their absence or null value is missing evidence. Receipt FAIL, hash mismatch,
duplicate/unknown applicability cell, invalid schema, forbidden fields or corrupt
structure is FAIL. Decision reasons retain FAIL and PENDING details; FAIL
dominates. No hidden data fields such as answers, seed_map,
archive_path/archive_contents, source_code or heldout_data are accepted.

## Deferred

Independent record delivery, actual identity/signature verification and archive
read denial, all-20-cell semantics, rights/licence approval and validator negative
case/runtime qualification are PENDING - needs Roy. D1 integrates the facade into
CLI; trusted-ID input and preservation of FAIL/PENDING are explicit reconciliation
items. No execution is authorized by installing/importing this validator.
