# Public and trusted interfaces

Dirty Mode source construction; runtime unverified. API inventory baseline:
82d099767b3603692dc5bd11a1327cba546b81ef. Canonical definitions and validators
own detailed behavior; this map is not instrument or independent acceptance.

| Layer | Canonical source | Boundary |
| --- | --- | --- |
| Public task/recovery evidence | rlab.contracts | PublicTask, Target, Intent, Transition, HistoryRead, FailedAction; no expected effects |
| Closed actions | rlab.actions | Action, Mutation, parse_action, validate_action; kind-dependent wire fields |
| Public observation | rlab.snapshot, rlab.views | Snapshot/validate_snapshot; Page is the development public HTML/target projection |
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

Current D1 trusted backend/loop bridge, D2 broker/original prompts and D3 development
matrix runner are IN PROGRESS, outside this pinned inventory. Their final source
composition needs reconciliation; no implementation/acceptance is claimed here.
Follow the owning documents for details:

- [Host/recovery](HOST-RECOVERY.md): executor, browser and authority seams.
- [CLI](CLI.md): missing ports, command dispatch and trusted report loading.
- [Admission](ADMISSION.md): external anchors and independent gates.
- [Offline provider](OFFLINE-PROVIDER.md): request/cost binding and public action loop.
- [Evaluation](EVALUATION.md): operator reports and integrity anchors.
- [Limitations](LIMITATIONS.md): deferred qualification.

Independent authorship, custody, rights, all twenty admission cells, installed
wheel exclusion and P11 instrument qualification remain pending. Construction
does not retroactively satisfy the frozen plan's preimplementation order.
