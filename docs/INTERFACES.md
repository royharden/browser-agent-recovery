# Public and trusted interfaces

Dirty Mode source construction; runtime unverified. API inventory baseline:
f57099f16de021c776d367afcc1c00ef966a70e3. Canonical definitions and validators
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
The checker declares public_records PUBLIC without actor/worker/controller
exceptions. See [schema mapping and current scan](CONTRACTS.md).

Canonical activation still has MISSING privileged implementation:
SourceProfile.require_activation and OwnedWorker.start refuse. No-argument
worker.main refuses, while explicit WorkerConfig/WorkerCapabilities now select
the accepted bounded public-channel control loop and typed owner/client source.
This does not provision descriptors, start isolated workers or qualify enforcement.
The in_process_convenience adapter implements none of those privileged mechanisms.

Accepted BrowserAuthorityIPC, PlaywrightBridge and BrowserReceiptPeer now provide
both application sides of the fixed browser receipt protocol. The checker declares
their three exact operator modules trusted ENTRY roots AND forbidden public
dependency targets. Operator-only media_capture has the same entry/dependency
classification. The combined scan reports 41 modules, 19 public roots,
20 transitive modules, zero findings/unknowns and exit 0. Actual authenticated
connections/context, OS isolation and browser effects remain unprovided or unqualified.

The fixed source callsites are now joined:

- PlaywrightBridge.interact calls the actual-event recorder before IPC interaction
  retrieval; create_browser_peer_composition binds that recorder to
  BrowserReceiptPeer.record_interaction and its retained authority-clock record.
- The peer's installed_snapshot observer calls PlaywrightBridge.project_snapshot,
  a DOM-only read without authority clock/IPC reentry into the serialized peer.
- BoundBrowserPeerHTTP calls peer.dispatch_http with the captured context
  capability; TaskHost's receipt_sink retains the real LocalTaskPort terminal
  receipt before HTTP response delivery. A listener/context authentication is
  not supplied by this composition.
- Executor's counted prepare/observe/refill path reaches prepare_submission on
  the submitted native ref's CURRENT form. F2 Body is restored from immutable
  original public intent; readonly quantity is compared, not filled. Operations
  consume shared caps/deadlines and retain partial Step provenance. This adds no
  common semantic target search for R0/R1 and fabricates no interaction receipt.
- Private framing bounds the length prefix and fixed DTOs. The explicit
  browser_peer_in_process profile is convenience wiring. Constructing the composed
  BrowserSession itself performs a framed clock bootstrap, so it was not invoked
  as a no-effect construction check.

See HOST-RECOVERY's latest peer-composition section for this accepted join;
BROWSER-RECEIPT-PEER's earlier D2 handoff list describes its package boundary
before those D1 callsites were added, not the current missing-source inventory.

The accepted D3 evaluation.source_schedule producer is now consumed by fixed
CLI/backend source. It returns ready/pending/refused based on independent full-input
anchors and typed admission. This is an implemented source path; no artifact was
generated, and no research freeze or independent receipt exists. Final source
pins await final accepted byte composition/line endings.

Canonical privileged infrastructure is still UNPROVIDED: preauthenticated inherited
connections and listener/body/context binding, inherited-FD provisioning, distinct
UID/GID launch, namespaces/mounts/ACL/egress, whole-descendant termination, separate
scorer access and hard preemption of blocking code. Qualification probes and external
independent admission/rights/prompt inputs are also UNPROVIDED or UNQUALIFIED.
These are not supplied by typed callbacks, object identity, framing or static scans.
Opt-in P7 media lifecycle source is now wired into PlaywrightBridge and trusted
session/backend composition; capture defaults disabled. MediaStatus and ContextReceipt
keep their shapes, and no private capture policy/artifact/manifest/result type enters
actor schemas. Playwright tracing starts with sources disabled, stops before context
close, and video completion is inspected after successful context close. Completed
receipts require actual nonempty regular no-follow files with observed stable size
and SHA256 under declared inspection budgets; partial/error/unavailable/not-requested
states stay distinct. No trace, video or manifest was generated here.

Rich paths, errors and trace ZIP metadata stay in private manifests/operator results.
The evaluator receives only actual completed safe-relative JSON manifest/video refs
under an explicit private report root; ZIP is not a supported evaluator link. Failed,
partial and unselected bytes are retained without deletion. Actual operator failure
selects media; success uses the stable paired key's SHA256 modulo 10 bucket. This is
nominal deterministic selection, not an observed 10% sample or a storage reduction;
unknown outcome/key retains uncertainty and available media. Report verification
covers reported metadata integrity, not the current raw ZIP/video bytes or their
privacy. Native writer, ACL/race, disk quota and runtime behavior remain unqualified.
Follow the owning documents for details:

- [Host/recovery](HOST-RECOVERY.md): executor, browser and authority seams.
- [Trusted boundary](TRUSTED-BOUNDARY.md): refused entrypoints and offline pipe source.
- [Receipt peer](BROWSER-RECEIPT-PEER.md): bounded private protocol and retained terminal evidence.
- [CLI](CLI.md): missing ports, command dispatch and trusted report loading.
- [Admission](ADMISSION.md): external anchors and independent gates.
- [Offline provider](OFFLINE-PROVIDER.md): request/cost binding and public action loop.
- [Evaluation](EVALUATION.md): operator reports and integrity anchors.
- [Matrix](MATRIX.md): development scheduling, lifecycle and provenance sidecars.
- [Limitations](LIMITATIONS.md): deferred qualification.

Independent authorship, custody, rights, all twenty admission cells, installed
wheel exclusion and P11 instrument qualification remain pending. Construction
does not retroactively satisfy the frozen plan's preimplementation order.
