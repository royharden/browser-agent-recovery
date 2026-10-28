# Browser receipt peer (source only)

`rlab.browser_receipt_peer.BrowserReceiptPeer` is the privileged server half of
the fixed `browser_ipc.py` protocol. Construction starts no socket, HTTP server,
browser, task reset, database or process. This source has not been imported or
executed. It provides neither authenticated provisioning nor isolation or hard
preemption. All runtime/security qualifications remain open.

## Fixed composition

```python
peer = BrowserReceiptPeer(
    task, allowed_origin,
    context_capability=operator_context_capability,
    installed_snapshot=read_actual_privileged_dom_snapshot,
    interaction_receipt=lookup_actual_retained_interaction,
    control_timeout_ns=1_000_000_000,
    max_requests=4096,
)
```

The task is an existing `DevelopmentTask`; the peer reuses `LocalTaskPort` and
`TaskHost`. The origin is the existing exact loopback HTTP origin with explicit
port. The opaque context capability is an operator object checked by identity.
A typed object, a callback, or claimed metadata does not establish authentication.
The embedding must authenticate the inherited channel and bind the actual HTTP
browser context to that exact object out of band. No actor-selected endpoint,
path, file descriptor, task, run, admin operation or private spec is accepted.

`exchange(BrowserRequest)` is a serialized convenience in-process endpoint.
`exchange_frame(frame, deadline_ns)` is its fixed byte endpoint; the outer and
inner absolute deadlines must match. `serve_once(connection,
context_capability=...)` serves one frame on an already connected AF_UNIX socket
object supplied by the operator. It never binds, listens, connects or launches.
The operator must verify peer credentials/context, exclusively own the socket,
and provide OS isolation. This source does not perform that authentication.

Frames have a four-byte unsigned big-endian length, maximum 131072 payload
bytes. The socket reader validates the prefix before payload read/allocation.
Exact frame length, closed DTO fields, operation-specific payloads, unique JSON
keys, integer numbers, finite JSON, bounded targets/payload pairs and no trailing
JSON are required. No pickle, arbitrary class loading or plugin deserialization
exists. Responses use only known immutable public DTOs; oversize output fails
rather than truncates. Socket IO uses a bounded monotonic control timeout; normal
response IO also respects the caller authority deadline. Clock calls have the
fixed `authority-clock` ID/deadline zero and separate bounded control IO. The
source cannot preempt arbitrary blocked task or callback code; a real operator
supervisor must qualify that later.

## HTTP and terminal receipts

The authenticated operator HTTP dispatcher calls
`peer.dispatch_http(operator_context_capability, environ, start_response)`.
It must choose the capability from its privileged connection/context binding,
never from an HTTP header, cookie, form field or actor-supplied selector.
Ambient `rlab.intent_context` is removed. Only a successful fixed IPC `bind`
installs the original `IntentContext` for exactly one next POST. A consumed POST
cannot be replayed even when its body, navigation or response delivery fails.
GET render/history cannot replace a prepared projection. No reset/seal/admin
route is added.

`TaskHost` has one narrow optional constructor `receipt_sink`. It calls this
trusted sink with the actual `LocalTaskPort.execute` terminal receipt before
serializing/delivering the HTTP response. The existing exact admitted public
form validation is unchanged. `DevelopmentTask.action` still derives the actual
target from current refs; there is no common row/name guard for R0/R1.

`completed` returns only the retained actual server receipt matching run, epoch,
clock, request and original root. It can return a retained receipt even after
the navigation/action deadline. Missing completion causes explicit timeout/halt;
no previous receipt, client-clock time, zero time or no-effect claim is invented.
A dispatch exception without a terminal receipt stays unknown, retains its
binding and halts further actions. Cleanup failure likewise retains preparation
and halts. A late real terminal receipt remains available for reconciliation.
Unknown attempts are retained in the peer alongside terminal receipts, bounded
by the request cap; these are transport lifecycle records, not a second task or
authority store.

IPC has a nonblocking serialized owner lock. HTTP does not acquire that lock.
Completion waits on a condition that releases the shared state lock, allowing
HTTP receipt capture/unwind. A completion delivered while HTTP response delivery
is still unwinding keeps the binding until dispatch finishes; another preparation
cannot race that dispatch. Bounded waiting uses both authority deadline and a
separate monotonic control cap. The fixed clock request itself cannot provide
hard preemption of a stalled clock implementation.

## Public preparation and ordinary interactions

Prepare invokes the existing task preparation once for the request ID and returns
only a public replacement projection, with an opaque one-use installation ID.
For remaps the projection includes ordinary controls and buttons in fixed DOM
order. Installed compares both the submitted projection and an independently
read actual privileged DOM projection against the expected URL, epoch and target
identities before acknowledging. HTML serialization normalization is not used as
an identity test. A second installation or same-ID preparation is refused; no
second remap is fired. Fault preparation records originate in the existing task;
real browser installation qualification requires the trusted observer and this
installed acknowledgement, not the task record alone.

An IPC `PublicInteraction` is not an accepted action receipt. The privileged
ordinary-action dispatcher must call
`peer.record_interaction(capability, request_id, PublicInteraction(...))` only
after actually observing the accepted action (or actual uncertain result),
before the corresponding IPC interaction request. This hook stamps authority
time and retains the receipt. Alternatively `interaction_receipt(request_id)`
may supply an already retained genuine trusted receipt. The peer checks exact
bindings, public URL/status, time and deadline, and returns the actual record.
No receipt is manufactured from the IPC claim. IDs reserved by the actual-event
hook cannot be taken by prepare/history; exactly one interaction consumption is
allowed. Missing actual producer data causes explicit unbound/halt.

## Required joins and deferred qualification

These remain explicit source/composition work outside D2 ownership:

- D1 must wire the actual ordinary-action completion hook (or an equivalent
  genuine retained receipt producer). The accepted Playwright client currently
  calls IPC `interaction` directly; without this join it fails closed.
- D1 must preserve already filled public form values across remap `set_content`
  (or reapply the admitted payload before POST). F2 task markup contains an empty
  required body; installing it currently erases a previously filled textarea.
  The peer does not fabricate that field or loosen the admitted form check.
- Trusted composition must supply the actual installed DOM observer and call
  the context-bound HTTP adapter. A nominal callback is not authentication or
  proof that a real browser/context is connected.
- D4 owns explicit boundary-layer/source-map registration of this new trusted
  module if required by the final checker policy. No checker/schema edits are
  included in this package.

External provisioning remains: authenticated inherited peer/context capability,
peer credential verification, HTTP body/read supervision, supervisor preemption,
OS isolation/namespace/ACL/egress policy, real browser/transport activation and
runtime evidence. There is no source claim of canonical readiness, independent
approval, freeze, security receipt, or model/evaluation performance.

Validation for this package is AST/diff/manual static review only. No tests,
application imports, codecs, peer/client exchanges, sockets, DBs, listeners,
network, model calls or processes were run. Spend USD 0; runtime unverified.
