# Trusted boundary source — runtime UNVERIFIED

Canonical activation is deliberately unavailable. `SourceProfile.require_activation()`
validates configuration and always refuses with concrete missing hooks. No caller
boolean, empty process slot, in-process adapter or source review qualifies isolation.
`construction_report()` says `canonical-source-unjoined`, never PASS. No process,
listener, browser, Linux denial probe or test was executed during construction.

`SourceProfile` requires distinct positive nonroot authority/worker UIDs and GIDs,
three separate provisioned mode-0700 authority-owned absolute DB/socket/output roots
outside OneDrive, no symlink components, no writable ancestors, and bounded caps.
Validation never recursively chmods/chowns, creates roots or migrates files. These
pathname checks still require deployment descriptor/mount pinning against rename
races. The caller must use a contained fixed filename for Authority's DB; Authority
itself has not been changed to enforce this profile.

`OwnedWorker.start()` refuses. `launch_plan()` only describes fixed isolated Python
module argv, no shell, no inherited environment, closed descriptors, no passed FDs
and empty supplementary groups. It never accepts actor commands. The minimal
environment consists only of literal locale/hash settings. UID dropping, authority
subprocess launch, namespace setup, mounts/ACLs, browser descendants, network denial,
trusted IPC and real admission are unjoined. Direct-child `stop()` source retains
only its own Popen handle and uses bounded terminate/wait/kill/wait; it cannot prove
descendant termination. No public API accepts a PID or arbitrary executable.

`worker.decode_action()` reuses the closed public `actions.parse_action` protocol,
rejects duplicate JSON members and nonfinite constants and caps frames at 16 KiB.
It exposes no SQL, shell, reset, seal, upload, tool, environment or admin command.
`read_action()` needs a future deadline-enforced transport; it is not itself a
preemption mechanism. `worker.main(config, capabilities)` now supplies the fixed public control loop
described below. A standalone invocation refuses absent inherited capabilities.
This composition API does not establish isolation or canonical activation.

`PrivateAdmin` is an explicitly labelled in-process development adapter. Its
`bind_development()` requires Linux authority UID/GID, private root and SO_PEERCRED;
only exact matching peer UID/GID may issue bounded newline JSON requests. There
are no public HTTP admin routes. At most 64 requests are accepted; each has a
1 KiB input cap and a three-second transport deadline. Existing sockets are
preserved and rejected. Only the selected new socket is chmodded to 0600; no
ancestor permissions change. `close()` closes the handle without unlinking paths.

Only `{operation: reset, family: F1|F2|F3, seed: 0..999}` and `{operation: seal}`
are accepted. Reset delegates to `DevelopmentTask`/`Authority.setup` for fresh
run/epoch; it never replaces an unsealed task. Seal delegates to `Authority.seal`.
The injected `require_worker_stopped` callback must stop/acknowledge all owned
worker descendants before either operation. A callback or `OwnedWorker`'s empty
slot is not proof of isolation. Admin is not yet joined to the actual browser
bridge/task used by a canonical run.

Seal writes an exclusive no-follow authority-generated filename under output root,
at most 1 MiB, mode 0400, flush/fsync before announcing the receipt. It returns a
receipt path/digest to the private operator, never the worker. Future scorer access
is a read-only file under the same authority UID; separate scorer ACL/UID plumbing
is unjoined. The digest is Authority's existing bundle digest, not an isolation or
scorer acceptance claim. If serialization/export fails after sealing, no output
success is claimed and the operator must reconcile the sealed run; no retry reset
can silently manufacture replacement evidence. Partial outputs are preserved.
The adapter retains its sealed receipt and active run on every export failure;
reset stays refused. A repeated seal request retries that same frozen receipt
without resealing Authority, using an exclusive `-export-N` basename so partial
files are never overwritten/deleted. State clears only after successful fsync.
Process-restart recovery of that in-memory pending export remains unjoined.

Before canonical activation: implement privileged authority/worker launch, exact
descriptor closure and UID/group drops, fresh per-run browser context/namespace,
read-only trusted code mounts, authority/worker filesystem separation, egress allow
policy, bounded whole-worker termination and trusted browser receipt IPC. Then
authorize and perform actual Linux UID/ACL/egress/FD denial probes, cancellation,
deadline, peer credential, output durability and read-only scorer checks. All remain
UNVERIFIED. In-process convenience source is not a sandbox.

## Inherited offline pipe construction (r5)

`worker.InheritedPipe(read_fd, write_fd, owner_uid, codec=BrokerCodec())` is an
operator-installed capability. It accepts dedicated Linux FIFOs only, owned by
the configured nonroot owner, with exact read-only/write-only access flags and
already nonblocking descriptors. It opens, duplicates, reconfigures and closes no
FDs. The operator must supply the correct two unidirectional ends to each process
and retain their exclusive lifetimes so descriptor numbers cannot be rebound.
No endpoint path, descriptor selector or cap is accepted from a worker frame.

Pipe reads take exactly the four-byte big-endian prefix, check the trusted
BrokerCodec body cap before reading or allocating the body, then read at most
4096 bytes per iteration. Writes independently validate one canonical bounded
frame and use at most 4096-byte writes. Selectors wait on actual nonblocking FIFO
readiness with absolute Linux monotonic deadlines, rechecked on each iteration.
EOF, partial I/O failure, malformed/oversized input and unknown completion are
terminal for the owner/client stream; there is no drain, retry or resynchronization.
Framing failures terminate before broker dispatch; accepted codec frames use the
broker's existing bounded attempt accounting. The owner stops reading whenever
`BrokerClosed` or `broker.closed` applies, including after sending the final reply.

`TrustedPromptConfig` freezes operator model, Limits, LoopLimits, exact externally
cleared prompt hashes, arm/source/stage and at most sixteen requests. It provides
no live/provider/plugin/endpoint selector. `OfflinePipeOwner(endpoint, provider,
profile=..., config=...)` retains only accepted built-in offline broker/provider
objects on the privileged side. It checks prompt clearance before touching the
provider. Missing clearance raises PromptUnavailable; caller must retain the
requested scheduled row as not_executed rather than dispatch or substitute arms.

The sole authorization operation is owner-only
`capture_and_authorize(action_port, request_id, deadline_ns,
trusted_previous_feedback='')`. It selects the cleared profile before touching
the clock or observation; validates a fresh trusted ID and bounded authority
deadline; calls the real trusted ActionPort.observe; requires PublicObservation
and its matching clock_id; renders D2's accepted prompt messages from that exact
observation plus operator-retained ordinary feedback; makes the fixed-model/schema/
limits ProviderRequest; and calls broker.authorize_request. It returns detached
public wire data only. A fresh owner is required for each run/epoch/clock. Trusted
previous feedback is an operator input, never taken from worker request fields.

`serve_once(deadline_ns)` never authorizes. It serializes access through a
non-reentrant lock, rejects duplicate/rebound worker IDs, uses the authorized
request's original deadline when shorter, and calls accepted broker.handle_frame.
Broker compares all messages/schema/observation/model/limits against the installed
binding and consumes it before its single provider invocation. The same ID cannot
be reauthorized or replayed after rejection, dispatch or uncertain completion.
Unknown outcomes stay unknown; no timing, usage or paid-accounting receipt is
invented. A final provider result can be retained privately even when pipe delivery
times out. The worker receives no attempt ledger, provider or authorization method.

`WorkerPipeClient(endpoint).request(public_request, deadline_ns)` receives only a
bounded pipe capability, rejects extra request selectors and duplicate IDs, and
checks response version/request/observation/schema correlation. Its stream is
serialized and capped at sixteen calls. Model/schema/limits authorization remains
the private broker owner's job. The lower-level legacy public action decoder
remains distinct from this accepted provider framing protocol.

These are joined application SOURCE contracts only. No FIFO was opened, read or
written; no codec, broker, prompt, loop, provider, process or test was executed.
The standalone worker entry still refuses because actual inherited-FD provisioning,
supervisor launch and isolated fresh browser context are unjoined. Explicit
operator composition now has the joined public-channel source described below. The authority clock and pipe deadline must share Linux's monotonic
domain; clock/FD ownership and descriptor lifetime require runtime verification.
In-process observe/provider calls cannot be forcibly preempted by selector checks;
privileged process containment and hard cancellation remain missing. Canonical
UID/ACL/namespace/egress/scorer qualification and external admission remain refused
or pending. This source adds no S3 accounting, live SDK or security PASS receipt.


## Fixed worker composition (r6; source only)

`worker.main(WorkerConfig, WorkerCapabilities)` drives actual bounded capture,
accepted `WorkerPipeClient.request`, closed action validation and public execution.
`WorkerConfig` pins run/epoch/clock, the existing 40-step/16-call/180-second maximum
limits, a positive request timeout capped at 30 seconds and bounded wait duration.
`WorkerCapabilities` accepts exact `WorkerPipeClient` and `PublicActionPipe` objects,
with separate inherited streams. It accepts no authority, private spec, admin,
provider, broker owner, authorization handle, callback, plugin or endpoint loader.
Actor frames cannot select descriptors, files, endpoints or capability classes.

`PublicActionPipe` uses the existing bounded length-prefix codec and inherited
nonblocking FIFO operations. Its only operations are `capture` with an empty
payload and `execute` with one closed provider action. Replies correlate exact
version/operation/request ID. Each loop ID is deterministic and fresh within the
pinned run's dedicated stream; the owner rejects repeats. Capture returns only
the exact public observation and public broker request. Worker checks digest,
run/epoch/clock, snapshot, literal allowlisted path and wait cap before execution.
Finish requires a correlated ordinary acknowledgement and is not server success.

`PublicActionPipeOwner(endpoint, action_port, offline_owner, config=...)` is the
concrete privileged counterpart. Its `serve_once(trusted_deadline_ns)` captures
and authorizes via the accepted offline owner using the actual trusted action
port, and forwards that same capture through the owner's private observation
slot; it never recaptures a potentially different snapshot. The separate offline
owner serves the broker exchange before the public owner serves execution. Public
requests never authorize arbitrary messages or supply authority clock/deadline
fields. Only one capture can be pending; execute consumes it before invoking the
actual `ActionPort.execute`. The owner independently checks all action bounds,
run/epoch/clock, step/call/time caps and feedback identities/times. Ordinary
feedback is retained privately for the next cleared prompt; worker fields cannot
substitute it. The worker never receives either owner object.

Worker results retain bounded observation, full broker reply and latest public
reply plus error text per attempted iteration, including provider failures and
unknown transport outcomes. Owner records retain request/reply/error when possible,
including a reply whose delivery failed. A malformed frame or uncertain operation
closes its stream with no resynchronization/retry. The caller retains returned
results and terminal owner records; no durable artifact or qualification receipt
is written by this loop. Exceptions during configuration validation are refusals,
not execution outcomes. Descriptor disposal remains the operator's responsibility.

This is source composition, not a privileged launcher. No Boolean attestation,
fake isolation token or bypass of `SourceProfile.require_activation()` was added.
No-argument `python -m rlab.worker` still refuses. Canonical activation remains
refused until genuine privileged isolation/descriptor/context enforcement exists;
passing ordinary Python capabilities does not qualify that enforcement. The two
owner channels require trusted scheduling and hard process cancellation supplied
by that later infrastructure. Linux monotonic-domain equality, FIFO ownership,
browser effects, joined concurrency and all runtime behavior remain unverified.
