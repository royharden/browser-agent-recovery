# Development faults and public history

Source construction only. No runtime, browser, matrix or isolation checks have
run. Only F1/F2/F3 are implemented. Independent admission and custody remain
pending Roy; this source is not a study instrument acceptance.

The operator can construct `DevelopmentTask(authority, family, seed,
fault=FaultPlan(kind, boundary=1), lag=HistoryLag(delay_ns=2_000_000_000))`.
Omit both options for the existing clean/immediate behavior. Supported lag is
0 or 2 seconds; reconciliation budget B belongs to recovery policy, not lag.
Do not give the worker the task object, authority, configuration or fault rows.

The executor captures the original page/intent, allocates a trusted request ID,
and calls `prepare_action(request_id)` once before the semantic submission.
R0/R1 retain the original snapshot/ref. R3/R23 fresh-observe and resolve after
preparation, preserving original semantic intent and form fields. The same
request ID then goes to the unchanged `action(intent, ref, snapshot_epoch,
request_id, origin)` signature. Preparation is idempotent only while that
submission is pending; mutation is never deduplicated. Retry uses another
request ID and calls preparation again. Rejected/refused R3 resolution must
call `cancel_action(request_id)` before returning or selecting another action.
This releases the local pending submission; an unissued interrupted action
stays not_fired. It does not rearm a fault or undo a fired expiry/remap.
Existing simple callers can omit preparation: action prepares as a fallback.
That fallback is insufficient for an R3 guard performed before preparation.

Faults select one positive semantic submission ordinal. Snapshot/history reads
do not increment it. The operator must freeze the same eligible boundary across
arms; no seed schedule, private answers or onset is returned to the actor.

- EXPIRED_VIEW invalidates the captured view, stamps authority onset and rejects
  before mutation with `ValueError("EXPIRED_VIEW: refresh before submission")`.
  It remains a rejection for the selected submission even if R3 refreshed.
- STALE_ID rotates refs consistently in HTML and the Target projection, keeping
  the snapshot epoch valid so an old ref silently denotes another row. A fresh
  observe changes refs/epoch as usual. `acknowledge_remap(Page)->bool` is an
  optional trusted callback: a browser transport must install the supplied page
  and acknowledge before returning true. Without a callback the in-process page
  installation is its local acknowledgement only, not a browser receipt.
  Onset is stamped after acknowledgement. Insufficient distinct refs or failed
  acknowledgement stops preparation and leaves a harness-error marker for seal.
- INTERRUPTED_ACTION stamps the fault in the same SQLite transaction as the
  attempt/effect, commits, then raises
  `TimeoutError("INTERRUPTED_ACTION: confirmation unavailable")` with no success
  dictionary. This is a fixed lost-confirmation interstitial seam, not a TCP
  failure. Orders/tickets repeat normally; already-deleted F3 rows record another
  attempt but no second deletion effect.

Successful action return is unchanged: `changed: bool`, `state_version: int`,
`request_id: str`. Invalid snapshot/ref/payload is ValueError, with no committed
mutation. Other unexpected adapter/storage failures are harness failures; never
infer known absence from them. Use `Authority.now_ns()` for trusted response
timing with `Authority.clock_id`. The transport must stamp after producing its
actual terminal response, not before handling the action.

The ordinary route calls `DevelopmentTask.history(request_id)`, delegating to
`Authority.history(task, request_id, visible_through=None)`. Configured lag
applies even to direct authority history; legacy visible_through can restrict a
prefix further but never reveal rows ahead of lag. One read transaction binds
started/completed timestamps, clock ID, latest and served watermarks and the
complete unfiltered transition prefix. Reads are uncached and request IDs must
be trusted/fresh; the recovery parser still rejects reused IDs. No scheduled
onset, selected boundary, lag setting, request lineage or private answer is
included. Deletion transitions remain visible after the item disappears.
N<M is lag, never proof of absence. N=M alone also does not prove absence: the
existing public parser still requires fresh post-response timing, contiguous
versions and complete successful unfiltered data. No sleeping/polling occurs in
these modules. History and actions remain unavailable after sealing or a clock
domain change.

Visibility uses a separate trusted timestamp sampled after SQLite COMMIT
returns, not the earlier effect-processing timestamp. Thus a slow transaction
cannot consume the 2-second visibility delay. The serialized authority keeps
these anchors in process memory, exports them under digest-covered `visibility`
with version and clock ID, and refuses cross-process run reuse. A missing anchor
withholds that transition and every later one; later qualification must treat a
missing sealed anchor as harness-unknown. This is source design, not a durability
or concurrency qualification. Default zero lag exposes committed transitions on
the next ordinary read.

Operator seal adds `fault` to the existing digest-covered evidence v1 bundle:
run/epoch/clock, kind, ordinal, seen, selected request, status, onset and snapshot
plus disposition fired/not_fired and harness_error. A never-reached armed fault
is not_fired; an unfinished selected boundary is not_fired with harness_error.
Clean runs have kind/status clean and no injected onset. This additive record
requires later evaluator/schema reconciliation; it never enters public history.
The existing effects/attempt sequences and state version scheme are unchanged.

Deferred: transaction/rollback and clock tests, all fault/arm/lag combinations,
fresh/cached/partial/alias history probes, HTML form/browser acknowledgement,
R23 cancellation and retry wiring, process isolation, held-out admission and
independent scoring. No held-out families, numerical results, API keys, runtime
setup or deployment infrastructure are supplied.
