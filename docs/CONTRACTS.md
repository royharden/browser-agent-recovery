# Public contract projection

Version 2.0.0 is source-only. No schema files or runtime results were generated.
rlab.public_schema derives definitions using stdlib AST parsing, without evaluating
annotations or importing selected types. scripts/export_contracts.py is a later
activation entry point; it was not executed during Dirty Mode.

The sole allowlist is public_schema.RECORDS: public task, target, intent,
transition/history, failed action, driver action/mutation, snapshot, development
page and bound action/interaction receipts. Only fixed contracts.py, actions.py,
snapshot.py, views.py and ports.py plus generator bytes are read. No arbitrary
module/type/plugin loader or recursive source discovery exists.

Each dataclass maps to a closed object in $defs under module.ClassName. Every
field is required, including constructor defaults: this describes a COMPLETE
serialized record. str/int/bool/float map to JSON scalars; Literal to enum;
T | None to union; tuples to arrays, with prefixItems/exact length for fixed
tuples. Known imported public types resolve to references. Unsupported annotations,
missing/duplicate classes, unsupported declarations/inheritance or recursive aliases
abort export. Unknown shapes never become permissive objects.

The bundle root deliberately rejects every instance. Consumers select an explicit
fragment, for example urn:rlab:public-records:2.0.0#/$defs/contracts.PublicTask,
registering the bundle as a resource with a JSON Schema 2020-12 validator.
Tuple-to-array conversion remains the serializer's obligation.

Annotation projections omit semantic validation: string/byte caps, sorted unique
payloads, versions, ref roles, same-run/clock checks, routes and kind-dependent
wire fields require the canonical validators. actions.Action is neither the
parser's command dictionary nor providers.Action. Provider wire schemas remain
owned by rlab.providers.port.action_schema(); no second schema copies it.
EventEnvelope is explicitly unsupported: there is no canonical typed public
event record. Trusted events/seals are separate [operator evidence](INTERFACES.md).

Bundles carry raw-byte SHA-256 for each source file and the generator, a version
and stable schema identifier. Identical bytes yield identical sorted JSON; no
timestamps are used. Consumers compare hashes to their approved source checkout,
review changed definitions AND validators, and bump the version when publishing
an incompatible projection. Hashes expose changes; they do not approve them.
Line-ending changes affect hashes.

Later, with a reviewed trusted package installation matching the checkout:

```text
python scripts/export_contracts.py --checkout <reviewed-checkout> > <private-output>/public-records-v2.json
```

Do not run that command in this Dirty phase. Later validation must exercise export,
reference resolution, serializers, unsupported-shape refusal, source-change
detection and the closed validators together. Reconcile final D1/D2 source before
publishing any generated output.

## Static boundary guidance

scripts/check_boundaries.py parses bounded public/dependency Python source and
packaging TOML without app imports. Actual scan counts, violations and unresolved
dependencies are distinct. Its policy and exact trusted exemptions are declared
in source. It is static guidance only; it cannot qualify worker UID/ACL/egress,
secret denial, custody, admission, installed wheel contents or runtime isolation.
Packaging findings must be repaired by the packaging owner, not suppressed to
produce a clean report. See the script's --help for later operational usage.

The packaging policy now explicitly excludes `rlab.evaluation`, `rlab.heldout`
and `rlab.held_out`, including all their package descendants. Package-data
inclusion is explicitly disabled; ordinary runtime Python modules, including
admission, providers, agents and public_schema, retain the existing discovery
rule. Top-level operator evaluation is outside the `src`/`rlab*` discovery scope.
This narrows intended discovery; it does not attest to private files' existence
or absence. Future intentional resource files need an explicit packaging review.

At the earlier packaging-repair composition the unchanged checker parsed 27 modules,
13 public roots and 14 transitive modules, with zero violations/unknowns and
exit 0 (`static_scope_clear`). This closes the earlier six hypothetical package
inclusion findings and default package-data unknown at the source-policy level.
It is not an installed-wheel, runtime isolation or independent acceptance result.
Wheel build/content inspection and final combined-source reconciliation remain
deferred; the public event-envelope gap remains explicitly unsupported.

## Combined-source reconciliation

Accepted base `7ef166751b1a64f36dfddedd7287938373128643` adds `Page.controls`:
the complete record now requires a separate tuple of ordinary public controls,
alongside mutation-button targets. The existing tuple/Target derivation handles
this field automatically. Version 2 is an incompatible complete-record projection
because version 1 lacked that required field. No artifacts of either version
were emitted. Other allowlisted record declarations remain unchanged. Raw source
and generator hashes are computed only on later export; they are not a frozen
research source pin. Final pins wait the final accepted bytes/line endings.

The initial unchanged scan of this combined base found 36 modules, 18 public
roots, 22 transitive modules, 78 path-qualified policy violations and four
undeclared operator layers; exit 2 (`incomplete`). Exact new operator entrypoints
admin_socket, dev_backend, supervisor and trusted_bridge are now declared trusted
ENTRY roots and forbidden as public dependency targets. No actor/recovery/provider
or worker root was exempted. The final scan retains all 78 violations, zero
unresolved items and exit 1 (`violations`), with the same module/root/closure counts.
Packaging intent has no current findings; installed-wheel validation is deferred.

The findings arise from `agents.session_codec` imports of `executor.ExecutionResult`,
`executor.Step` and `ports.ActionReceipt`/`InteractionReceipt`. Eager export in
`agents.__init__` propagates those imports through agent modules and worker roots;
executor also imports trusted ports. Counts include repeated paths from different
public roots. D2/INT must reconcile the public-record versus trusted-code seam,
for example by relocating the record definitions or trusted codec boundary under
a separately owned grant. D4 does not modify that implementation or exempt it.
This is a declared static-policy failure, not a demonstrated runtime vulnerability
or a reason to call the full application complete.
