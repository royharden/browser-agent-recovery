# Host and recovery source integration

This package is construction source only. Runtime, browser transport, isolation,
mutation/fault behavior and the study instrument have not been qualified. No
model rows are measured. Independent data admission, custody, challenge tables,
licensing and study acceptance remain PENDING - needs Roy.

## Host and trusted adapter

`TaskHost` is a provisional stdlib WSGI callable, with no listener or startup
entrypoint. The frozen plan calls for Starlette; transport replacement and real
browser/HTTP integration remain deferred. It serves only the configured task
page, ordinary transition history and the task's form submission route under an
exact loopback HTTP origin with an explicit port. There is no reset, seal,
private-state or administrative route.

A POST requires a server-injected `rlab.intent_context` holding the original
admitted intent, trusted request ID/origin and absolute deadline. Incoming HTTP
headers and form fields never create that context. An unbound POST returns 503.
The form must contain exactly the admitted original payload, reference and
snapshot; duplicates and extra fields are rejected. Bodies are limited to 8192
bytes/eight fields, same-origin POSTs are required, and each request is bounded
by the earlier of its trusted deadline and a three-second method allowance.

A later trusted bridge must bind context to the current executor/task and each
request, prevent actor access to WSGI environ, enforce request/body read timeouts,
restrict its listener to the approved loopback address, and apply process/ACL and
egress controls. Checking the deadline after a body read cannot interrupt a
blocking WSGI read. These are integration assumptions, not proven protections.

`LocalTaskPort` is trusted in-process development wiring. Its authority object
and task object must never be given to a worker. It delegates observations and
mutations to `DevelopmentTask`; history must use `DevelopmentTask.history(id)`
so task-owned lag/fault behavior is retained. There is no direct-authority-history
fallback. DL2's accepted producer baseline `5ace58b` supplies this task history
method and has been merged for static consumer reconciliation. The confirmed
r3 seam also supplies `Authority.now_ns()`, and `LocalTaskPort.now_ns()` delegates
to it so method deadlines and response timing share the authority clock domain.
Clock identity and monotonic-clock assumptions still require runtime qualification.

For guarded R3/R23 actions, the executor calls
`prepare_action(request_id, deadline_ns)` before fresh observe/resolve, then uses
the same request ID for execute. This delegates to
`DevelopmentTask.prepare_action(request_id)` with deadline checks before and
after. Task action performs fallback preparation once when omitted by R0/R1/R2;
there is no common semantic guard or double preparation. A successful
`changed=false` dictionary is acknowledged as a legitimate no-op, not treated
as an automatic retry trigger.

If fresh resolution refuses, or the executor exits before issuing a prepared
mutation, `cancel_action(request_id)` releases the pending submission. It is
trusted non-effect cleanup, exempt from browser-operation admission so it can
run after an expired deadline or an exhausted cap. Result metadata records
cancelled request IDs. Cleanup failure is harness-unknown. An issued action
consumes its preparation, even when confirmation is lost; it is never cancelled
as a substitute for history reconciliation. A local preparation that overruns
its deadline cancels before propagating the timeout.

Cleanup failure has a distinct `PreparedCancellationError` port contract. The
local adapter retains its pending marker and propagates that error, including
when cancellation follows a pre-dispatch deadline or preparation overrun.
The executor preserves `pending_cleanup_request_ids`, returns `harness_unknown`
without history reconciliation or mutation retry, and refuses further port
operations until a trusted owner reconciles the pending state. It does not
automatically retry failed cleanup. This metadata is separate from confirmed
`cancelled_request_ids`; failed cleanup never counts as successful cancellation.
The WSGI surface returns a service-unavailable error for this condition. These
are source guarantees requiring later runtime qualification.

The producer installs deterministic STALE_ID remaps before guarded observation
and reuses preparation for the same request ID; current source has no asynchronous
onset after resolution. Its default acknowledgement is local page installation,
not a real browser acknowledgement. A future transport must supply the trusted
`acknowledge_remap(Page)` callback and qualify the asynchronous boundary race.
Failed acknowledgement remains a producer harness-error marker, not a fired
successful browser event.

The confirmed task seam reserves `ValueError` for pre-effect expired-view or
missing-reference rejection, which yields a `failed` receipt. Other exceptions
after dispatch yield `unknown` because a mutation may have committed before
confirmation was lost; in particular, interrupted-action `TimeoutError` occurs
after commit. A returned action
status can be `acknowledged`, `failed`, `unchanged` or `unknown`; unrecognized
status and deadline overrun remain unknown. An unknown receipt never proves
absence; `failed` relies on the confirmed pre-effect exception contract, not
independent effect evidence. Request identity and authority-clock receipt timing belong to
the trusted bridge, never actor-provided headers or client timestamps.

## Recovery executor contract

The executor retains immutable original operation, target semantics, payload,
root-intent identity and pre-action public version. Re-resolution changes only
the issued reference/snapshot. Form fields come from the original intent, never
from private answers or a refreshed default form.

- R0 returns native action results without an automatic wrapper retry.
- R1 repeats the same failed/unknown/unchanged action once after 250ms. It retains
  the captured reference; common validation does not add semantic identity checks.
- R2 reconciles against ordinary public transition history and retries once only
  after a fresh complete unfiltered read proves absence. Lag, cache, repeated or
  partial reads, aliases, multiple matches and uncertain timing are ambiguous.
- R3 uniquely resolves fresh role/name/row-context identity before mutation,
  refusing missing or ambiguous matches. It adds no R2 retry.
- R23 combines the semantic guard and reconciliation, including a fresh unique
  resolution before its single retry. Original payload and target semantics stay
  unchanged throughout.

The same executor accounting applies across arms: at most 40 total port
operations (including observations, history probes, waits and retries), a fixed
180-second run deadline, and at most three seconds per method. The reconciliation
window defaults to four seconds from the failed response and never resets after
a retry. All additional probes/actions/waits consume steps and elapsed time.
Recovery-window exhaustion yields ambiguous abstention; genuine method or run
cap overruns take precedence and remain cap aborts. A history timeout before its
method deadline is unsuccessful/incomplete evidence, never an empty-success read.
No elapsed timeout alone proves absence. The 40-operation interpretation is
stricter than a mutation-only action count and must be checked for profile fit
later; it is not evidence that a future live-model request profile fits.

This source seam covers mutation forms and public observations/history. The full
closed browser bridge for navigation, click/fill/select/back/reload/finish,
allowlisted URL/method handling, snapshots, media and worker isolation is still
deferred. No actual Playwright, browser context or server has been started.

## Deferred validation

Later authorized owners must exercise all five arms and fault/lag combinations,
retry/deadline/action accounting, original-field retention, stale silent remaps,
empty/partial/cached/alias/multiple-match history, already-deleted no-op attempts,
and host origin/route/form/context/body/deadline rejection. Also qualify the real
browser/HTTP bridge, blocking-read timeouts, trusted lineage binding, Linux
worker ACL/egress and archive-denial probes. P2/P5 custody and independent
qualification cannot be replaced by agent source review. Runtime stays
unverified; no tests, imports of application code, services, installs, Docker,
credentials, network/model calls, spend or publication were performed here.

## Closed browser consumer source (r3)

`actions.py` accepts only click/fill/select/goto/back/reload/wait/finish with
closed field sets, exact types and bounded strings/waits. Mutation clicks carry
captured public operation/target/form/version intent; no hidden expected effects.
`snapshot.py` rejects oversized snapshots instead of truncating them (64 refs,
16KiB body, 32KiB body plus visible target text), requires unique refs and matching
snapshot epoch, and checks only captured control roles for action applicability.
It does not compare new DOM identity for native R0/R1. Only the recovery guard
freshly re-resolves semantics for R3/R23.

`routing.py` permits an exact configured loopback origin and the current task's
GET page/history and POST action routes. Other origins, admin/other-run paths,
encoded/traversal/query/fragment routes, redirects, downloads and uploads are
refused. This policy must be installed on every request by a real backend; a
lexical policy and post-navigation check are not egress isolation proof.

`browser.py` provides a typed `TrustedBridge`/`BrowserAdapter`/`BrowserSession`
consumer. No default backend, Playwright import/startup or direct HTTP exists.
The mandatory missing hook must create and attest a fresh context, enforce all
resource routes/methods and event behavior, extract public DOM snapshots, supply
authority-bound mutation/history/read timing and lineage, honor deadlines and
acknowledge actual remap installation. Ordinary browser timeouts do not synthesize
authority events. Media metadata records unqualified/not-requested/error states.
In-process facade access is not a secure worker boundary.

Non-mutation browser interactions use the same executor operation/time budget as
observations/history/mutations/recovery. Mutation clicks retain the existing
five-arm path and pending-cleanup halt. finish means actor termination only,
never server success. Navigation requires another captured snapshot before ref
actions. F2 scripted fill needs a public Body textbox from the future DOM snapshot
hook; the foundation's button-only projection is insufficient and is not silently
upgraded to a successful fixture. Provider/admission and real browser/worker hooks
remain unavailable until separately implemented and qualified.

An exception from `TrustedBridge.execute` is an `UnboundActionResponse`, unless
it is the separately typed pending-cancellation failure. A browser timeout does
not establish terminal server response timing. The controller records the request
under `uncertain_request_ids`, halts as `harness_unknown`, and does not synthesize
an ActionReceipt, probe history, cancel the possibly issued mutation or retry it.
Only an actual identity-bound authoritative terminal receipt can enter R2/R23
reconciliation. The halt is latched before fallible final clock accounting and
blocks further controller operations; the facade also terminates on unknown/cap.
Trusted operator reconciliation of in-flight requests is a later required hook.

## Explicit development bridge and loop adapter (r4 source)

`create_development_session(task, origin, **limits)` is an operator-only opt-in
for InProcessDevelopmentBridge. ContextReceipt.profile is explicitly
in_process_convenience; BrowserSession rejects it unless allow_convenience=True.
The logical namespace is fresh but is never a browser/isolation attestation.
Media is unavailable. No default browser bridge or canonical activation exists.

Page.controls adds visible Body textbox refs separately from Page.targets.
Driver action/remap still consumes button targets only, preserving native
silent-remap behavior. Projection keeps form values public/escaped and uses
ordinary task.history; no private DB version or seal enters snapshots.
session.close is idempotent logical stop, not OS worker death or rollback.

Executor and BrowserSession observe/history/act now accept caller absolute
deadlines; mutation and interaction methods accept request correlation. Every
issued deadline is at most the caller/run/method bound, including R1 waits and
R2/R23 probes/retries. Correlations are bounded ASCII alphanumeric/dash/underscore,
recorded once per controller; repeated IDs cannot mint another mutation. Initial
request ID reaches preparation and action unchanged; automatic retry IDs stay
trusted-generated. Root intent and immediate origin remain controller-owned.

TrustedActionPortAdapter is an explicit loop seam, not a BrowserSession alias.
It requires a trusted LoopCodec for D2's accepted Action/observation/feedback
shapes; default None refuses. It preserves exact caller ID/deadline, maps only
actual receipt timing into feedback and uses None for missing response time.
The final D2 codec/shape binding is unjoined until producer acceptance; no
provider/agent module is imported by this adapter. Canonical worker/authority
IPC, resource route enforcement and real browser acknowledgment remain pending.
Aggregate loop feedback leaves response_ns unset when a final retry is uncertain
or cleanup is unresolved; an earlier terminal receipt remains in the result but
cannot stand in for the final issued request's missing completion.
