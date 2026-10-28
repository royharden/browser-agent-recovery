# Public contract projection

Version 2.1.0 is source-only. No schema files, source schedule, research freeze or
qualification receipts were generated. The current accepted application source
pin is f57099f16de021c776d367afcc1c00ef966a70e3, before D4's media map update.
Canonical definitions and validators remain implementation truth.

## Derivation and compatibility

rlab.public_schema uses stdlib AST parsing without importing/evaluating selected
types. public_schema.RECORDS is the sole fixed class allowlist: contracts.py,
actions.py, snapshot.py, views.py and public_records.py. Those files plus generator
bytes are read; there is no arbitrary module/type/plugin loader or source discovery.

The public_records source owns frozen ActionReceipt, InteractionReceipt, Step and
ExecutionResult, plus Arm/Disposition literal aliases. Legacy ports/executor exports
alias those exact classes in source; their Python class module changed to
rlab.public_records. Annotation/decorator/default fields of allowlisted records
are unchanged in the final peer/callsite delta. Schema mapping remains 2.1.
The subsequent media delta changes neither these allowlisted records nor the
MediaStatus/ContextReceipt class ASTs. Operator media policies, private artifact
paths/manifests/results are not new actor schema targets.

Each class maps to a closed object under $defs/module.ClassName. All fields are
required, including constructor defaults, because this describes a COMPLETE
serialized record. str/int/bool/float map to JSON scalars; Literal to enum;
T | None to union; tuples to arrays, using prefixItems/exact length for fixed
tuples. Known public imported types resolve to references. Unsupported annotations,
missing/duplicate classes, unsupported declarations/inheritance and recursive aliases
abort export; unknown shapes never become permissive objects.

ports.ActionReceipt and ports.InteractionReceipt schema names remain references
to public_records.ActionReceipt/InteractionReceipt. This preserves closed receipt
record shapes without copying definitions. The compatibility names are schema
fragments, not runtime alias/serializer verification. Step/ExecutionResult and
canonical receipt names were additive in 2.1. Version 2 already included the required
Page.controls tuple separately from mutation targets.

The bundle root deliberately rejects every instance. Consumers register the bundle
with a JSON Schema2020-12 validator and select a concrete fragment, for example
urn:rlab:public-records:2.1.0#/$defs/contracts.PublicTask. Tuple-to-array conversion
remains the serializer's obligation. Annotation schemas omit semantic validation:
byte/string bounds, sorted unique payloads, versions, ref roles, same-run/clock
checks, routes and kind-dependent wire fields require canonical validators.
actions.Action is neither the parser's command dictionary nor providers.Action;
provider wire truth remains rlab.providers.port.action_schema().

No private BrowserPeerComposition, authority/peer/IPC/context controls, private task
specifications, expected effects, answers or seeds enter actor schemas. A canonical
typed PUBLIC event envelope is still absent and explicitly unsupported. Trusted
seal/event dictionaries are not promoted to a public truth API.

## Reproducibility and later export

Bundles contain raw-byte SHA256 of canonical public source and generator, a version
and schema identifier. Identical bytes produce identical sorted JSON without
timestamps. Consumers compare hashes to their approved checkout and review changed
shapes AND validators; incompatible projections require a version change. Hashes
expose changes, not approval. Line endings affect hashes. Final source/generator
pins await final accepted composition; no final pin receipt is minted here.

Later, with a reviewed trusted installation matching the checkout:

```text
python scripts/export_contracts.py --checkout <reviewed-checkout> > <private-output>/public-records-v2.1.json
```

Do not run this in Dirty Mode. Export/reference/legacy-fragment resolution,
serializers, runtime exact-class identity, unsupported-shape refusal and source-change
handling remain unexercised. No generated JSON is claimed to exist.

## Current static boundary guidance

scripts/check_boundaries.py parses bounded Python source and packaging TOML, never
imports the application. public_records is explicitly PUBLIC. Exact operator ENTRY
modules browser_ipc, playwright_bridge, browser_receipt_peer and media_capture are also forbidden
public dependency targets; trusted declarations never exempt actor/worker closure.
Other exact layer declarations remain in the checker as the single policy source.

The affected actual combined scan reports 41 modules, 19 public roots, 20 transitive
modules,zero violations,zero unresolved,exit0 static_scope_clear. This supersedes
the earlier 27/37/39/40-module snapshots. Only the accepted source delta justified this
scan; no unchanged repeat or synthetic test was run. AST imports conservatively
include TYPE_CHECKING/function/conditional paths. Reflection, arbitrary loader alias
changes and runtime import-path mutation cannot be proven by this analysis.

Packaging explicitly excludes rlab.evaluation/heldout/held_out and descendants,
with include-package-data=false. Legitimate admission/providers/agents/public_schema
remain included; top-level evaluation is outside src/rlab discovery. Actual installed
wheel contents/resource needs remain unverified. Static clear proves no worker UID,
ACL,egress,authentication,custody,admission,clock or runtime isolation property.

See [interfaces](INTERFACES.md) for the current producer/observer/receipt/field
and media lifecycle source map and still-unprovided canonical activation requirements.
Media completion receipts describe inspected actual files only after later capture;
partial or retained paths do not imply completed artifacts. Rich private ZIP/manifest
data is separate from the evaluator's closed safe-relative JSON/video references.
Neither report metadata integrity nor an unexecuted source hash authenticates raw
media bytes, privacy, runtime capture, native writer quotas or filesystem/ACL behavior.
