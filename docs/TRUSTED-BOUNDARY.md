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
preemption mechanism. `worker.main()` refuses until enforcement/public IPC/browser
context are joined. MAX_ACTIONS is a declared bound for that future loop, not a
claim that an unimplemented loop currently accounts for actions.

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
