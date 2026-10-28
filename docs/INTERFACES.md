# Public and trusted interfaces

Dirty Mode source construction; runtime unverified. API inventory baseline:
05e209f4f1c85f62d907916340bc684c207cab6f, with D4 public-record schema synchronization.
Canonical definitions and validators
own detailed behavior; this map is not instrument or independent acceptance.

| Layer | Canonical source | Boundary |
| --- | --- | --- |
| Public task/recovery evidence | rlab.contracts | PublicTask, Target, Intent, Transition, HistoryRead, FailedAction; no expected effects |
| Closed actions | rlab.actions | Action, Mutation, parse_action, validate_action; kind-dependent wire fields |
| Public observation | rlab.snapshot, rlab.views | Snapshot/validate_snapshot; Page separates mutation targets from controls such as the Body textbox |
| Recovery | rlab.recovery | verify, resolve, Reconciliation; visible evidence only |
| Public receipts/results | rlab.public_records | ActionReceipt, InteractionReceipt, Step, ExecutionResult, Arm and Disposition; trusted adapter still supplies identity/timing |
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

The accepted public-record extraction removes the prior codec-to-controller
dependency path: agents.session_codec now reads canonical public_records.
Legacy ports/executor exports alias those exact classes; class __module__ now
names rlab.public_records. No wire field/default/decorator changed in extraction.
The public-record sync checker declared public_records PUBLIC and reported 37 modules,
19 public roots and 20 transitive modules, zero findings/unknowns, exit 0. No
actor/worker/controller exemption was added. This is a static source result,
not an installed-wheel or runtime isolation result. See [schema mapping](CONTRACTS.md).

Canonical activation still has MISSING privileged implementation:
SourceProfile.require_activation and OwnedWorker.start refuse. No-argument
worker.main refuses, while explicit WorkerConfig/WorkerCapabilities now select
the accepted bounded public-channel control loop and typed owner/client source.
This does not provision descriptors, start isolated workers or qualify enforcement.
The in_process_convenience adapter implements none of those privileged mechanisms.

Accepted browser_ipc.BrowserAuthorityIPC and playwright_bridge.PlaywrightBridge
now provide fixed operator-side receipt-client/browser adapter source. The checker
declares these two exact trusted ENTRY modules and forbids public imports of them;
no actor exception was added. The combined scan reports 39 modules, 19 public
roots, 20 transitive modules, zero findings/unknowns and exit 0. Actual transport,
authenticated receipt peer, OS isolation and browser effects remain unqualified.
The next browser_receipt_peer implementation is NOT accepted at this pin; it
receives no speculative checker declaration or clean-source claim.

The accepted D3 evaluation.source_schedule producer is now consumed by fixed
CLI/backend source. It returns ready/pending/refused based on independent full-input
anchors and typed admission. This is an implemented source path; no artifact was
generated, and no research freeze or independent receipt exists. Final source
pins await final accepted byte composition/line endings.
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
