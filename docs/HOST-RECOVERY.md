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
