# Provisional offline evaluator

Source construction only: no evaluator, report generation, test, model, browser,
service or study has run. Independent oracle, arithmetic, admission, licence and
instrument qualification remain PENDING - needs Roy. All private truth is supplied
by an external operator. No hidden instances, answers, seeds or family-specific
held-out implementation are authored here.

`evaluation/` stays outside `src/`. The existing setuptools finder uses only
`src/`; wheel exclusion is source-inspected, not installed-wheel qualification.
No actor module imports the evaluator and no authority DB is opened here.

## Facade for the later CLI owner

`evaluation.report.build_report(schedule, records, *, pins, config, price) -> dict`
validates frozen inputs and rebuilds outcomes, scheduled tables and contrasts.
`evaluation.report.report_html(report) -> str` emits escaped static HTML.
`evaluation.report.verify_report(report, *, expected_pins,
expected_inputs_sha256) -> True` recomputes the entire report and raises ValueError
on mismatch. Verification requires EXTERNAL retained anchors; an internally
consistent document cannot prove its own original inputs.

Standalone source entrypoints are `scripts/report.py INPUTS NEW_PRIVATE_OUTPUT_DIR`
and `scripts/verify_report.py REPORT EXTERNAL_ANCHORS`. These are future commands,
not commands executed in this phase. The report entrypoint refuses to overwrite an
existing output directory. No installed CLI wiring is supplied in this package.

Inputs JSON has exactly `schedule`, `records`, `config`, `price`, `pins`. Config
has integer `bootstrap_seed`, positive `resamples` (default recommendation 10000,
maximum 100000), and `horizon_ns=180000000000`. Price is an external JSON mapping,
even for a keyless profile; it supplies no spend/access approval. Pins are SHA256
strings for exactly `source`, `schedule`, `oracle`, `config`, `price`.
`evaluation.freeze.implementation_pins()` hashes the local evaluator Python file
inventory plus both scripts, and oracle.py bytes; the other pins are canonical
JSON hashes of their inputs. Freeze and retain actual pins externally before
execution; the functions do not fabricate research acceptance.

A schedule row has exactly these nonempty string labels: `schedule_id`, `block_id`,
`variant`, `family`, `condition`, `arm`, `mode`, `stage`, `model`, `source_kind`.
Conditions are `clean`, `EXPIRED_VIEW`, `STALE_ID`, `INTERRUPTED_ACTION`; arms are
R0/R1/R2/R3/R23/RP. Family and variant labels are metadata only, not instance
construction. `source_kind` is authored/scripted/mock/live; only live uses
`mode=live`, others use fixture. Stage is explicit (for example dev/pilot/main or
diagnostic/planted-parser); never mix diagnostic rows into a standard stratum.
A block binds one family/variant/condition across arms. Bootstrap clusters bind
family+variant across all conditions/arms. No schedule is generated from observed
successful runs. All absent records remain not_executed in scheduled denominators.

`records` maps schedule_id to exactly `seal`, `spec`, `execution`, `cost`, `reads`,
`media`. Omit a key for a not-executed row. For a dispatched run whose evidence is
absent/corrupt, include its record with seal null: it becomes harness_unknown.
Execution has exactly `run_id`, `epoch`, `clock_id`, `start_ns`, `termination`,
`actions`, `model_calls`, `failures`. Counts/start can be null when unavailable.
Termination/failure labels preserve aborted/provider/cap stops. Counts must include
all wrapper operations/model attempts, including failed calls, not just successes.
An aborted run with complete valid evidence is still scorable; status valid means
evidence-valid, not goal success. Oracle terminal_status separately says success,
incomplete or harness_unknown.

The seal is the exact `Authority.seal()` mapping from accepted 5ace58b: bundle and
sha256. Digest verification includes fault and visibility fields. The adapter
requires run/epoch/clock consistency, contiguous attempt/effect sequences and effect
versions, matching mutation attempts, state transition consistency and a sealed
terminal marker. A valid empty history with nonempty expected effects is incomplete
with missing effects. Absent/corrupt evidence is unknown. A missing visibility
anchor makes timing harness_unknown; known positive harm remains a lower bound.

External private spec has exactly:

- `initial_state`: authority-shaped list of `{id, deleted}` rows.
- `expected_effects`: multiset list of exact `{kind, target, payload}` signatures,
  with payload a JSON object rather than authority's canonical JSON string.
- `forbidden_effects`: nonempty match patterns over kind/target/payload. A pattern
  may omit fields; supplied payload matches the complete object.
- `ordered_effects`: exact signatures required in order as a subsequence.
- `terminal_predicates`: exact `{item_id, deleted: bool}` predicates.

The current source state adapter understands the accepted authority's order,
ticket and delete events and item deletion state only. Other transition adapters
need a separately granted interface extension; it does not implement hidden-family
semantics or assert full-study support. Extra effects remain in history, so later
compensation never clears duplicate/wrong flags. Repeated delete without mutation
is an attempt, not a second effect. Ordering/terminal failure remains separately
visible even if the effect multiset matches.

Cost has exactly state, known_usd, unresolved_usd; money values are nonnegative
decimal strings or null. States: known_zero (keyless current execution only),
known, unknown, reserved_unsettled. Settled states require explicit zero unresolved
liability. Replay source price/spend is external provenance, never silently assigned
to current execution. No missing amount becomes a settled zero. This consumes
receipts; it is not a ledger, a price lookup, or a budget-control implementation.

Reads are public history receipts with run_id/epoch/clock_id/request_id,
started_ns/completed_ns, served_version/latest_version, successful/complete/
unfiltered/cached/aliases. They come from trusted recording, never model narration.
Only fresh complete uncached successful ordinary reads can establish visible
confirmation. N<M never establishes absence. Read-version contents and transport
authenticity remain instrument qualification, not model self-report.
Watermarks must be a prefix of the sealed version history, and their latest
claimed transition must have a trusted commit anchor no later than read start.
Otherwise timing is harness_unknown, never confirmation before the effect.

## Analysis and release limits

Primary R23-R1 estimates remain separate for expiry and stale IDs; interrupted
actions are labelled controller-determined descriptive mechanism evidence.
R23-R0 is secondary; per-family rows remain visible. Complete-valid point estimates
include coverage, discordant counts, descriptive exact McNemar and fixed-seed block
bootstrap intervals. All scheduled unknown/missing counterparts remain in worst-case
difference bounds. Conditions share family+variant bootstrap draws. Empty coverage
is unavailable, never PASS. Success, cost, duration and within-arm excess against
the corresponding clean variant are reported alongside harm.

Latency uses one authority clock and a 180-second POST-ONSET horizon, separately
from total task duration. Already-correct effect state at onset has zero latency;
nonattainment, including early stop, gets the horizon, not harmless censoring.
Reached-only medians carry that label. Clean and not-fired rows have no artificial
onset. Missing timing stays unknown. Confirmation explicitly notes the counted-read
advantage of R2/R23. All public read/action costs belong in execution receipts.

Report JSON embeds input specs and sealed operator evidence for exact recomputation.
It is PRIVATE, not a publication artifact. Release/redaction of any hidden inputs
requires a separate decision. HTML escapes all text, contains no scripts, and only
permits relative local media filenames with approved inert extensions; absolute,
external, traversal, backslash and URL paths are refused. Media are not copied or
fetched. Browser/FS symlink isolation and real archive ACLs are unqualified.

Deferred validation: independent hand-worked oracle/overlapping flags/arithmetic,
full tamper matrix (metrics/attempts/events/pins/spec/schedule), latency horizon and
watermark probes, bootstrap and zero-coverage cases, report-only journey, real
media/path boundaries, packaging, private archive ACLs and source pin reproducibility
across line endings. Source hashes are byte hashes; rebuilding on another line-ending
profile requires a new externally frozen source pin. No numerical study outcome is
claimed by constructing this source.
