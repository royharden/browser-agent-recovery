# Keyless development matrix source

Construction only. No matrix, report, actor, model, browser, test or runtime check
has executed. Independent admission, oracle challenge tables, P5/P11 instruments,
source rights and custody remain PENDING - needs Roy. This source does not repair
the frozen plan's historical preimplementation order or grant execution.

`evaluation.matrix.development_matrix(profile, order_seed=0,
offline_source="mock")` defines original public development metadata only:

| Profile | Planned rows | Selection |
| --- | ---: | --- |
| scripted | 1,200 | F1/F2/F3 x four conditions x seeds 0..19 x R0/R1/R2/R3/R23 |
| naive | 240 | Same development cells, naive re-clicker R0 diagnostic |
| lag | 480 | INTERRUPTED_ACTION x L=0/2s x B=1/4s x seeds x R2/R23 |
| offline | 960 | Development cells x R0/R1/R23/RP; mock OR authored |
| planted-parser | 480 | Separate lag diagnostic, watermark-ignoring parser |
| misconfigured | 480 | Separate deliberately misconfigured lag diagnostic |

These numbers are planned denominators, never executed outcomes. Four conditions
are clean, EXPIRED_VIEW, STALE_ID and INTERRUPTED_ACTION. RP has 240 scheduled rows
in an offline matrix, all unavailable until original/cleared adapted prompt source
and admission exist. No WAREX text, hidden F4/FH instance, T2 seed, solver, private
answer or independent expected table is supplied. Diagnostic stages and IDs never
join standard rows. A planted parser/misconfiguration selector declares an intended
backend capability; it does not implement that backend or establish false absence.

The generator returns `{schema, profile, order_seed, offline_source, ordering,
schedule, metadata}`. `schedule` uses accepted evaluator's exact ten-field shape.
Sidecar metadata retains seed, task block, deterministic semantic fault-boundary
pair hash, lag/budget, control, actor/parser/configuration, lineage, availability
and separate unknown replay-source cost. All arms of a block have identical task
and fault selectors. Variants pair clean/fault cells. IDs include source/profile.
Ordering ranks blocks by SHA256 of `m18-matrix-order-v1:<order_seed>:<block_id>`,
then arms by the analogous schedule ID hash, with lexical tie breakers. Exact
regeneration validates content and order. This pairs task/fault, not model RNG.

## Trusted provisional producer contract

`evaluation.matrix_runner.run_matrix(inputs, admission=..., port=..., stop=...)`
accepts an operator-injected `MatrixRunPort`. D3 owns this consumer; D1 owns the
single-run producer. No import path, plugin, serialized code, shell, service or
artifact is loaded as executable code. Default backend is unavailable.

- `offline_only is True`, nonempty `clock_id`, monotone integer `now_ns()`.
- `reset(row, config) -> RunLease(schedule_id, run_id, epoch, clock_id,
  namespace, context_id)` creates fresh authority state/namespace/browser context.
  IDs cannot be reused anywhere in this matrix. Reset must clean up internally
  if it raises before returning a lease; runner stops on uncertainty.
- `execute(lease, row, config, deadline_ns) -> SealedRun(schedule_id, lease,
  record)`. `row` contains only public schedule and metadata; config has explicit
  caps, matrix deadline and input digest. No private spec is passed to the actor
  or backend. Producer must support the chosen profile/actor/parser/lag/budget and
  refuse unavailable capabilities before acting. No silently substituted profile.
- `close(lease)` releases that context without deleting archived run evidence;
  failure invalidates evidence and stops further dispatch.

Producer `record` is exactly `{seal, spec, execution, cost, reads, media}` matching
`evaluation.report.build_report`. Its `spec` slot is replaced by external private
operator truth in the evaluator, outside actor. Authority seal/run/epoch/clock,
family/condition, all-attempt counts and cost/read/media receipts must agree.
`not_fired` comes from sealed fault evidence, never a finish banner. All invalid,
failed and aborted operations must be in receipts. No paid provider code exists.

Input JSON has exactly `matrix`, external `specs` keyed by schedule ID, evaluator
`config`, external `price`, `pins`, `limits`, and `entrypoint_sha256` (actual operator
script byte SHA256). Missing spec means not_executed; malformed specs refuse before dispatch.
Limits are explicit positive integers: max_rows <=4000, max_actions <=40,
max_probes <=40, max_model_calls <=16, run_timeout_ns <=180000000000,
total_timeout_ns <=720000000000000. Mock/authored calls still count as attempts;
offline-only capability forbids paid/network dispatch, not mock model-call counting.
Backend must enforce steps/probes and synchronous reset/execute/close deadlines;
this wrapper cannot preempt blocking code. Runner pins the deadline clock domain
and checks clock regression, elapsed
deadline, action/model-call accounting and fresh IDs, stopping on unknown cleanup
or integrity. `stop()` prevents further rows; all remainder stays scheduled.
Ordinary backend aborts with complete sealed evidence stay scorable.

Typed `VerifiedAdmission` must come from an external trusted verifier, bind the
canonical digest of ALL inputs (including matrix metadata, private specs, limits
and report pins), and be PASS. Missing/PENDING dispatches nothing; FAIL skips ALL.
Hashes are provenance bindings, not proof of independent human custody. No code
here manufactures a verified PASS. The optional standalone script retains JSON
PASS as unverified and cannot dispatch without trusted verifier/backend injection.

The result contains the accepted evaluator report, every scheduled row's lifecycle,
raw returned records (including failures), matrix metadata, input hash and an
envelope hash. Evaluator absence remains not_executed; attempted reset/execute with
unknown evidence becomes harness_unknown. Invalid media is rejected inside the
per-row handler; raw response remains private and evaluator gets an unknown fallback,
so a malformed media receipt cannot discard the full matrix report. Execution
termination must be a nonempty string. Any rejected record is replaced by a
structurally safe unknown receipt, preserving its original JSON in raw_records.
Fallback identity fields accept only nonempty strings; invalid reset identities
become null rather than poisoning the private failure envelope's JSON encoding.
An unforeseen final evaluator error yields report=null plus report_error and
unreported_inputs with every scheduled row/record/config/pin for later repair;
it never fabricates metrics or loses the operator-private failure envelope.
Current offline known_zero must be an
explicit producer receipt; absent cost never becomes free. Authored/replay source
cost stays a separate provenance field and cannot be erased by zero current spend.
Raw errors/spec-bearing output is private; no media copied/fetched or external URLs
rendered. The accepted report verifier recomputes its embedded report against
external report pins/input hash; it does not authenticate matrix envelope metadata.

## Optional operator entrypoint and pins

Future invocation only, NOT executed during construction:

```text
python scripts/keyless_matrix.py --inputs <PRIVATE_INPUTS_JSON> --admission <EXTERNAL_ADMISSION_JSON> --anchors <EXTERNAL_ANCHORS_JSON> --output <NEW_PRIVATE_FILE_OUTSIDE_REPO>
```

No API key placeholder is required. All input paths and output parent are explicit
and outside product tree; output file is exclusively reserved before dispatch.
Existing files/symlinks refuse overwrite. Operator supplies private directory ACLs;
filesystem races and real isolation need later qualification. An unhandled fatal
error leaves the reserved file, never removes prior evidence. SIGINT requests
cooperative stop: the current bounded backend operation finishes, then remaining
rows are retained as not_executed; it does not forcibly preempt Python/backend code.
Durable streaming
checkpointing on process interruption is a later integration requirement.

Anchors are exactly `{pins, input_sha256, admission_sha256}` with canonical JSON
digests. Evaluator pins bind source/schedule/oracle/config/price. Existing source
inventory covers evaluator Python (including matrix modules). The separately
required `entrypoint_sha256` is checked against actual script bytes and bound by
the externally anchored full input digest and typed admission. Final source pins
still require the actual combined D1/D2/INT checkout, not this branch alone.
No frozen artifacts/results are generated by this source package.

Deferred: D1 reset/seal/clock/close producer and D2 actor loop joined implementation;
RP rights/prompt; external verified admission and all independent gates; final
combined source/entrypoint freeze; exact schedule arithmetic/order/diagnostic
separation runtime checks; stop/caps/deadline/hanging-backend and invalid seal/reset
cases; full attempt/cost/media retention and process-interruption durability;
report rebuild/tamper/private path/ACL/symlink/packaging checks; all matrices and
browser/isolation/performance/unit/integration/E2E qualification. Runtime unverified.
