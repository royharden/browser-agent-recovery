# Foundation interfaces (v1)

Original source authored by 0B14_Codex_gpt-61-sol_N20M1620DL3_M16-20-DL3,
2026-10-27. Synthetic widget/category strings are original development material.
No external tasks, upstream code, paper prompts, sealed answers or real people
are copied. Licensing and data admission remain pending; no licence is asserted.

`PublicTask` supplies goal/start path and public run/epoch. `Intent` captures the
original action's operation, target semantics, immutable fields and last public
version. It contains no expected outcome. Payload tuples must use sorted unique
field names. Each root intent keeps one `Reconciliation` for its entire lifetime.

`Authority` is trusted-only. It creates run/epoch/clock IDs, atomically records
attempts and actual effects, exposes ordinary history separately from `seal`,
and refuses mutation/read after seal or process-clock change. Reopening a DB
requires fresh runs, not cross-clock timing arithmetic. Each effect has sequence,
version, epoch, clock and request ID. Attempt root/origin comes from the trusted
executor, never a model-provided lineage label. Sealed state includes surviving
items and transition history for created orders/tickets. No scorer is supplied.

`DevelopmentTask` composes authority and original HTML for F1 order, F2 ticket,
F3 delete. `observe` refreshes refs. `action` maps the *current* ref to its actual
row and preserves original form fields, so the shared adapter does not silently
protect R0/R1 from wrong-row effects. It currently rejects old snapshot epochs;
silent ref remapping and scheduled faults require future driver/authority wiring.
There is no HTTP listener or worker process in this milestone.

R2 `verify` consumes ordinary complete transition history only. It rejects lag,
cache, partial/filtered reads, aliases, repeated request IDs, clock/run/epoch
mismatch, pre-response reads and non-contiguous versions. Exactly one matching
post-v0 transition is present; none is absent; multiple matches are ambiguous.
`Reconciliation.inspect` counts every probe, admits at most one retry before a
fixed 4-second default deadline and abstains when its step/time cap expires.
Driver must count probe/action costs and obtain fresh targets with `resolve`
before an R23 retry. While the retry is outstanding, inspection refuses to use
history. If that retry fails, call `retry_failed` with the trusted response timing:
freshness moves past that response but the original total deadline stays fixed.
R3 uses unique role/name/row identity; it refuses ambiguity.

Later transport wiring owns allowlisted local navigation, trusted timestamp and
lineage capture, history request IDs, current snapshot installation, action caps
and policy lifecycle. No arbitrary JS/HTTP/model tool belongs in actor contracts.
Never provide `Authority`, database handles, `seal` or lag controls to the worker.
R0/R1/R2/R3/R23 orchestration, fault/lag scheduling, server HTTP adapter, supervisor,
private oracle, custodian admission, provider and evaluation stay deferred.
