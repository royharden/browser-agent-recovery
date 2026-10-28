# Public and trusted interfaces

Dirty Mode source construction; runtime unverified. API inventory baseline:
7ef166751b1a64f36dfddedd7287938373128643. Canonical definitions and validators
own detailed behavior; this map is not instrument or independent acceptance.

| Layer | Canonical source | Boundary |
| --- | --- | --- |
| Public task/recovery evidence | rlab.contracts | PublicTask, Target, Intent, Transition, HistoryRead, FailedAction; no expected effects |
| Closed actions | rlab.actions | Action, Mutation, parse_action, validate_action; kind-dependent wire fields |
| Public observation | rlab.snapshot, rlab.views | Snapshot/validate_snapshot; Page separates mutation targets from controls such as the Body textbox |
| Recovery | rlab.recovery | verify, resolve, Reconciliation; visible evidence only |
| Bound receipts | rlab.ports | ActionReceipt, InteractionReceipt; trusted identity/timing supplied by adapter |
| Offline model seam | rlab.providers, rlab.agents | Authored mock/replay, request/result records, bounded loop and explicit action mapping |
| Operator commands | rlab.cli | Injected trusted ports and fixed optional evaluation loader; never an actor dependency |

The complete serialized driver Action dataclass differs from the dictionary
accepted by parse_action. Provider Action.operation differs from driver
Action.kind: use rlab.agents.map_action. Annotation schemas replace neither
closed validator. See [contract projection](CONTRACTS.md).

R0/R1 retain captured references without a common semantic refresh guard. R3/R23
explicitly re-resolve fresh role/name/row context. R2 permits absence only from a
fresh successful complete unfiltered same-clock read with matching watermarks
and contiguous versions. Timeout is never absence. Retry lifecycle, deadlines,
cancellation and uncertain completion belong to [host/recovery](HOST-RECOVERY.md).

Authority, DevelopmentTask and host/operator adapters are trusted. They own
DB/admin/fault/seal controls. Sealed bundles contain operator/scorer state,
attempt/effect events and visibility/fault metadata, not actor observations.
No canonical typed PUBLIC event envelope exists at this baseline. Export source
reports that gap instead of exposing authority dictionaries as public schemas.
Private TaskSpec/expected effects, schedules, hidden answers and seeds never
belong in actor definitions. Static dependency checks do not prove isolation.

The accepted composition now contains D1's explicit development session/backend,
TrustedActionPortAdapter and D2 SessionLoopCodec join, D2's offline broker/codec
and original prompt profiles, and D3's matrix lifecycle/provenance facade.
DevelopmentMatrixPort supplies preflight/reset/execute/close to that fixed facade;
JoinedDevelopmentOrchestration delegates through trusted embedding. Execution
requires genuine external admission, prompt clearance and operator factories.
These are source joins, not observed execution or canonical browser isolation.

Current static guidance reports a dependency-policy violation: agents.__init__
eagerly loads agents.session_codec, which imports trusted executor/ports modules.
Package initialization makes this closure reachable from public agent modules
and the worker. This owner reconciliation item has not been exempted; no runtime
isolation breach is established by the scan. See [checker status](CONTRACTS.md).

Canonical activation has MISSING implementation: SourceProfile.require_activation,
OwnedWorker.start and worker.main refuse; privileged launch, isolated browser IPC
and complete worker control wiring have not been joined. The explicit
in_process_convenience adapter does not implement these canonical paths.
JoinedDevelopmentOrchestration.freeze refuses instead of producing a source
schedule artifact. Final source pins await final accepted bytes and line endings;
no schema generation, actual freeze or independent receipt was performed.
Follow the owning documents for details:

- [Host/recovery](HOST-RECOVERY.md): executor, browser and authority seams.
- [Trusted boundary](TRUSTED-BOUNDARY.md): refused entrypoints and offline pipe source.
- [CLI](CLI.md): missing ports, command dispatch and trusted report loading.
- [Admission](ADMISSION.md): external anchors and independent gates.
- [Offline provider](OFFLINE-PROVIDER.md): request/cost binding and public action loop.
- [Evaluation](EVALUATION.md): operator reports and integrity anchors.
- [Matrix](MATRIX.md): development scheduling, lifecycle and provenance sidecars.
- [Limitations](LIMITATIONS.md): deferred qualification.

Independent authorship, custody, rights, all twenty admission cells, installed
wheel exclusion and P11 instrument qualification remain pending. Construction
does not retroactively satisfy the frozen plan's preimplementation order.
