# Operator CLI source

**Dirty Mode construction; runtime unverified.** These commands describe source
behavior for later activation; none was executed for this package. Python 3.12+
is the target. The package declares rlab = rlab.cli:main, has no runtime
dependencies, and excludes operator evaluation tooling from its source wheel.
No installation or environment setup is part of this milestone.

| Command | Source behavior | Current default |
| --- | --- | --- |
| tasks | List original F1 order, F2 ticket, F3 delete | Metadata only |
| run | External admission gate, then selected single-run development profile | PENDING, exit 3 |
| matrix | External admission gate, then injected D3 orchestration | PENDING, exit 3 |
| freeze | External admission gate, then injected D3 source-schedule producer | PENDING, exit 3 |
| report | Build JSON or static HTML through fixed operator evaluator | Unavailable if evaluator absent |
| verify-report | Verify against separately selected trusted anchors | Unavailable if evaluator absent |
| admit | Fixed lazy accepted rlab.admission producer with external anchors | PENDING without anchors, exit 3 |

run, matrix, and freeze default to --mode fixture --task F1 --policy R0
--max-actions 40 --max-probes 4 --horizon-ns 180000000000 --seed 0. Tasks are
closed to F1/F2/F3; policies are R0/R1/R2/R3/R23. Actions and probes are bounded
to 1..40, horizon to 1..180000000000ns and development seed to 0..999. The
trusted host must also enforce the shared executor's operation-specific limits.
The injected D3 matrix port owns schedule expansion; D1 does not generate a
competing schedule. Missing matrix/freeze orchestration returns unavailable
after admission. --mode live always refuses execution after the admission gate,
including when a provider port is injected. No command imports a user script,
loads a plugin from an artifact, or exposes arbitrary shell/JS/network tools.

FixtureRequest contains public selection/caps/seed plus operator profile,
condition and history lag. The latter controls stay in the trusted backend and
are never added to actor observations. FixturePort declares
run(request), matrix(request), and freeze(request), each returning a
PortResult(status, detail, artifact=None) with status complete/pending/unavailable/failed.
ProviderPort.readiness() is a declared future seam. Trusted Python embedding may call
main(argv, ports=OperatorPorts(...)). No command-line backend loader exists.
The normal console entry point binds AcceptedAdmissionPort, which lazily calls
the accepted rlab.admission.admit function. Missing external anchors remains
PENDING. No receipt, trusted ID or PASS is fabricated. There is no command-line
backend loader. The authored backend reuses run_scripted through the public
session surface; it does not inspect private expected answers.

run/matrix/freeze accept --manifest, --expected-hashes, --builder-ids and
--trusted-ids using the same independent anchor rules as admit below. All are
required for execution, together with an injected AdmissionPort. CLI gating
precedes custom fixture invocation, backend creation and live refusal. Explicit
FAIL returns exit 2 and skips every mode; PENDING returns exit 3. The backend
also gates direct trusted embedding calls before runtime imports or DB creation.

--profile canonical is the default and returns unavailable after admission:
actual Linux/browser enforcement hooks are not joined. Only explicit
--profile in_process_convenience selects the single-run source path. Condition
is --condition clean|EXPIRED_VIEW|STALE_ID|INTERRUPTED_ACTION, default clean;
--lag-ns is 0 or 2000000000, default 0. Condition/lag configure DevelopmentTask
on the trusted side and are not passed to run_scripted. A fixed loopback origin
in this embedding labels snapshots; it does not bind a port or start a server.

Convenience execution requires --db-root naming an existing absolute private
directory outside OneDrive and the product tree, without symlink/junction
ancestors. Every run exclusively creates a UUID directory and reserves its DB
without overwrite. Roots require operator-controlled private ACLs; lexical
checks and mode 0700 are not Linux ACL/network qualification. No paths are
deleted. The logical session must close before Authority.seal. No OS worker is
launched in this profile. Private record.json and seal.json remain in that
directory; authority seal contents are never actor observations. Scorer truth
is not supplied, and no oracle PASS is produced. Failures retain unknown/error
records where storage remains available. Current call cost stays unknown without
actual provider cost receipts. Models remain unmeasured.

DevelopmentOrchestrationPort declares matrix(request) and freeze(request).
It is injected into DevelopmentBackend only by trusted embedding. D3 must
retain every scheduled row, including unknown, errors and not-run remainder,
and stop on unknown hard failures. Freeze is a source-schedule artifact, never
a research freeze or independent receipt. No default orchestration is installed.
Trusted embedding may inject JoinedDevelopmentOrchestration(inputs=...,
admission=..., port=...). It delegates only to fixed
evaluation.matrix_runner.run_matrix; no second scheduler is added. Source-freeze
activation remains unavailable.

DevelopmentMatrixPort(authority, admission=..., profile=..., provider_factory=...,
action_port_factory=..., provider_limits=..., cleared_prompt_profiles=...) owns
one-row preflight/reset/execute/close. The operator retains one Authority for its
whole lifetime so all matrix deadlines share its clock. Preflight requires typed
external VerifiedAdmission PASS bound to the complete matrix input digest and
the D3 SealedRun provenance field. Offline actor rows additionally require exact
external prompt clearance and explicit operator factories/limits. Missing,
PENDING, FAIL, unsupported selectors or unavailable composition return D3's typed
UnattemptedRun before DevelopmentTask, context, provider or actor dispatch.
Default canonical profile remains unavailable.

Reset creates a fresh DevelopmentTask run/epoch/namespace and actual acknowledged
session context. It forwards absolute matrix/run deadlines into the executor.
Execute reuses reset's public start receipt, calls public run_scripted or accepted
run_offline, and closes the logical context before sealing. Cleanup uncertainty
halts reuse. Actor factories receive public schedule/metadata only; external
private specifications remain with D3, which binds the record's spec placeholder.
The evaluator record has exactly seal/spec/execution/cost/reads/media. Raw provider
attempts, source/current cost, null usage, rejected output and errors remain in
the separate rlab.run-provenance.v1 sidecar. Current known_zero requires actual
offline provider receipts; unknown accounting remains unknown. Missing or corrupt
attempted evidence stays harness_unknown, with no invented completion timestamp.
This is in-process source composition, with no process/browser/isolation claim.

The accepted D3 r2 sidecar uses explicit normalization of exact immutable provider
and loop dataclasses and tuples into native JSON. It requires equality of returned
provider receipts with the actual provider ledger, plus matching ledger/loop/
execution call counts. Partial coverage is unknown and stops D3 dispatch. Actual
USD current-cost receipts may be summed as supplied accounting; source-cost
receipts stay separate and no verified billing is claimed. Null usage remains null.
D3's private v2 envelope retains sidecars and requires external envelope and
provenance digest anchors through verify_matrix_envelope; verify-report alone
does not verify that sidecar. Unsupported or oversized provenance is retained as
bounded rejection metadata by D3, with an unknown attempted result.

Offline composition may bind action_port_factory with an explicit trusted lambda
calling create_offline_action_port(session, row, deadline,
cleared_prompt_profiles=operator_clearance). That helper is not auto-activated;
the exact accepted SessionLoopCodec and prompt inputs must be available before
reset. Missing fixed codec source returns UnattemptedRun during preflight.

Admission uses the accepted fixed lazy producer (or explicit trusted injection):

    admit(document, *, expected_hashes, builder_ids, trusted_ids=())
        -> AdmissionDecision(state, reasons), with to_dict()

The closed decision states are PASS, PENDING and FAIL. The CLI accepts
--manifest plus independently selected --expected-hashes, --builder-ids and
optional --trusted-ids files. Expected hashes are a JSON object with 1..64 keys
matching [A-Za-z0-9][A-Za-z0-9_.-]{0,63}, each mapping to one lowercase SHA256.
Identity files contain JSON lists of at most 128 unique printable ASCII strings,
each 1..128 characters without surrounding whitespace. Duplicate JSON object
keys are rejected. The manifest must be a different file from every anchor,
including symlink/hardlink aliases. Trusted identity provenance is externally
verified by the operator; self-declared receipt identities are not trust anchors.
Neither identity lists nor expected hashes are derived from manifest contents.

Missing hash/builder anchors, empty builder IDs, or omitted/empty trusted IDs
return PENDING with exit 3. A missing producer returns unavailable/exit 3.
An actual producer decision maps PASS to exit 0, PENDING to 3, FAIL to 2. The
console includes the explicit state, but withholds private reasons and inputs.
Admission PASS is not runtime acceptance. Exact actor codec installation remains
an operator composition requirement; unavailable codecs refuse before dispatch.

Report input flags are --schedule, --records, --pins, --config, and
--price, all separately selected JSON files. Schedule shape and private record,
config and price semantics belong to the evaluator. Pins require exactly source,
schedule, oracle, config and price keys containing lowercase SHA256 values. JSON
input is bounded to 16 MiB and rejects duplicate keys and non-finite constants.
Only the fixed lazy evaluation.report facade is imported, with these seams:

    build_report(schedule, records, *, pins, config, price)
    report_html(report)
    verify_report(report, *, expected_pins, expected_inputs_sha256)

Evaluator source is an operator installation/reconciliation obligation. Run from
a trusted environment/search path: Python's ordinary import machinery is not a
sandbox. The CLI never adds an artifact directory to sys.path, and actor/worker
modules must never import the evaluator. Missing evaluation source/dependencies
returns a precise unavailable response. Joined schemas remain provisional.

verify-report requires --report, --trusted-pins, and --expected-inputs-sha256.
The last flag names a small ASCII text file containing one lowercase SHA256 of
expected inputs. Both anchors must come from a trusted operator source selected
independently of the report; do not copy report fields into new files and treat
them as trust. The CLI rejects the report itself as either anchor and never
derives expected anchors from report contents. Only an explicit evaluator True
produces verification status. This checks integrity; it does not establish
runtime, oracle independence, admission or model quality.

report accepts --format json|html (default json), --private-dir, and --name
(default report.json). freeze also requires --private-dir, with default name
schedule.json. Output names must be plain filenames. Directories must already
exist outside the product source tree. Exclusive creation refuses overwrite.
The operator must establish private filesystem access controls and use a private
location; the CLI cannot infer ACLs or prevent a later external publication.
Reports may contain private specifications, seals, cost/read/media receipts and
operator evidence. Never move these artifacts into public fixtures, actor
observations, wheels or demo bundles. Even HTML remains private without a separate
release/redaction decision. Standard output emits status and output location,
not private report bodies or fixture payloads.

Exit 0 means metadata/command completion or anchor verification only; exit 3
means pending/unavailable; exit 2 means admission FAIL, refused inputs or integration errors
(argparse also uses 2). Readiness stays unknown, validation runtime_unverified,
and models not_yet_measured. Default unavailable paths report not_run. Future
trusted port completion is not a model/runtime PASS. Private exception messages
are withheld from console diagnostics.

Deferred: reconcile fixture/admission/provider producers and evaluator schemas;
validate caps and host clock/lineage; establish private artifact ACLs; exercise
missing-backend failures, default fixture, live refusal, output no-overwrite,
trusted-anchor verification and private artifact handling after Dirty Mode ends.

## Source-schedule operation (r6 source)

`freeze` delegates to fixed `evaluation.source_schedule.build_source_schedule`.
It requires `--source-inputs` (full original development matrix inputs),
`--source-expected-input-sha256` (independently selected digest text file), and
`--source-expected-hashes` (independently selected hash mapping). Exact hash keys
are matrix, schedule, metadata, specs, config, limits, price, pins, source, oracle,
entrypoint, admission. Input files cannot double as their anchor files. No digest,
source pin or approval is manufactured. No task or browser is run by this operation.

The trusted embedding supplies `OperatorPorts.source_schedule_admission`, an
actual externally verified full-input-bound admission object. A CLI JSON PASS
cannot construct it. Ordinary manifest admission and this full-input binding are
separate gates; absent full-input approval remains pending even after manifest
PASS. The facade returns ready/pending/refused; only ready produces an exclusive
private output using existing rules. Missing facade remains unavailable.
The artifact is a source schedule and reproducibility binding, not research
freeze, independent rights/data admission, signature or instrument acceptance.

Browser-peer composition is an explicit trusted embedding helper, not a new CLI
activation mode. create_browser_peer_composition requires the operator's existing
task/context capability and returns privileged handles plus a public session;
only a bounded public transport may reach a worker. Its browser_peer_in_process
profile is convenience, and session construction performs an in-process authority
clock bootstrap. Neither helper nor CLI has been executed under Dirty Mode.
Mounting/authenticating the fixed HTTP dispatcher and all canonical/runtime gates
remain separate. Source-schedule output retains its source-only meaning.
