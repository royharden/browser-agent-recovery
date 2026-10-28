# Operator CLI source

**Dirty Mode construction; runtime unverified.** These commands describe source
behavior for later activation; none was executed for this package. Python 3.12+
is the target. The package declares rlab = rlab.cli:main, has no runtime
dependencies, and excludes operator evaluation tooling from its source wheel.
No installation or environment setup is part of this milestone.

| Command | Source behavior | Current default |
| --- | --- | --- |
| tasks | List original F1 order, F2 ticket, F3 delete | Metadata only |
| run | Invoke trusted fixture host for one public task/policy | Unavailable, exit 3 |
| matrix | Delegate selected public task's policy matrix to trusted fixture host | Unavailable, exit 3 |
| freeze | Delegate schedule freezing; write returned private JSON | Unavailable, exit 3 |
| report | Build JSON or static HTML through fixed operator evaluator | Unavailable if evaluator absent |
| verify-report | Verify against separately selected trusted anchors | Unavailable if evaluator absent |
| admit | Delegate manifest decision to trusted admission port | PENDING/unavailable, exit 3 |

run, matrix, and freeze default to --mode fixture --task F1 --policy R0
--max-actions 40 --max-probes 4 --horizon-ns 180000000000 --seed 0. Tasks are
closed to F1/F2/F3; policies are R0/R1/R2/R3/R23. Actions and probes are bounded
to 1..40, horizon to 1..180000000000ns and development seed to 0..999. The
trusted host must also enforce the shared executor's operation-specific limits.
The matrix port owns expansion across R0/R1/R2/R3/R23 for the selected task;
policy is the baseline selection. --mode live always refuses execution,
including when a provider port is injected. No command imports a user script,
loads a plugin from an artifact, or exposes arbitrary shell/JS/network tools.

FixtureRequest contains only public selection/caps/seed. FixturePort declares
run(request), matrix(request), and freeze(request), each returning a
PortResult(status, detail, artifact=None) with status complete/pending/unavailable.
AdmissionPort.admit(manifest) returns the same type; ProviderPort.readiness()
is a declared future seam. Trusted Python embedding may call
main(argv, ports=OperatorPorts(...)). No command-line backend loader exists.
The normal console entry point injects no ports and never fabricates execution
success. The future fixture producer must use the public action/snapshot path;
these protocols do not implement a solver or hidden expected data.

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
means pending/unavailable; exit 2 means refused inputs or integration errors
(argparse also uses 2). Readiness stays unknown, validation runtime_unverified,
and models not_yet_measured. Default unavailable paths report not_run. Future
trusted port completion is not a model/runtime PASS. Private exception messages
are withheld from console diagnostics.

Deferred: reconcile fixture/admission/provider producers and evaluator schemas;
validate caps and host clock/lineage; establish private artifact ACLs; exercise
missing-backend failures, default fixture, live refusal, output no-overwrite,
trusted-anchor verification and private artifact handling after Dirty Mode ends.
