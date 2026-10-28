# Offline provider seam

Original stdlib source, Dirty Mode construction only; runtime unverified. This
package has no browser authority, network transport, SDK, key lookup or paid path.
Authored mock and authored replay are instrument inputs, never live-model evidence.

Import the public records from `rlab.providers`. The protocol is
`complete(messages, action_schema, model_id, limits, *, request_id, observation_digest)`.
Use the fresh dictionary returned by `action_schema()`; arbitrary schemas are refused.
Messages are a list/tuple of closed dictionaries with string `role` (`system`,
`user`, `assistant`) and string `content`. `model_id` is a label, not a live-model
approval. Request IDs are nonempty bounded strings and observation digests are
64 lowercase SHA-256 hexadecimal characters supplied by the trusted caller.
The module validates digest shape and binding; it cannot authenticate a caller's
observation or prove the digest describes it.

`Limits(max_messages=64, max_input_bytes=65536, max_output_bytes=8192,
deadline_ms=30000, max_wait_ms=5000)` has positive integer caps and hard ceilings
256 / 1048576 / 65536 / 300000 / 10000 respectively. Input byte accounting covers
canonical messages plus schema; output covers canonical action/error/usage data.
The deadline is a validated request shape only. Timing enforcement, worker/broker
isolation, concurrency and cancellation remain deferred; no clock measurements
or enforcement are claimed. Rejections have fixed diagnostics even when an
extremely small output cap cannot contain the diagnostic itself.

`Action(operation, ref=None, snapshot_epoch=None, value=None, path=None,
duration_ms=None)` accepts only click/fill/select/goto/back/reload/wait/finish.
Click requires ref and snapshot_epoch; fill/select additionally require value;
goto requires path; wait requires duration_ms; the remaining actions take no
other fields. Extra, missing, null wire fields and unrelated populated record
fields are refused. Paths must be local absolute paths without host, query,
fragment, traversal, backslash, encoded ambiguity or control characters. The
executor must still resolve refs against its current snapshot and constrain the
local route. Validation does not grant browser authority or imply task success.
Wait is 1..10000 ms and must fit the request's wait cap. No raw code/tool operation
is interpreted or dispatched.

`ProviderRequest` freezes canonical `messages_json`, `action_schema_json`, model,
limits, request ID and observation digest. `binding_digest` hashes that complete
record. Caller containers cannot later alter bindings. `ProviderResult` holds
request, exactly one action/error, raw_usage_json, provider_request_id,
actual_model_id, immutable timings, current_cost, source_cost, attempt_index and
mode and optional canonical `rejected_response_json`. `raw_usage` returns a newly decoded value; missing usage stays unknown,
reported usage is unverified. Actual-model identity stays absent for authored mock.

`AuthoredMockProvider(responses)` takes a bounded sequence of frozen Action or
ProviderError records. `ReplayProvider(entries)` takes frozen
`ReplayEntry(request, action=None, error=None, raw_usage_json=None,
provider_request_id=None, actual_model_id=None, source_cost=Cost('unknown'))`.
Replay binds the full canonical request including message/schema/model/request
ID/observation digest/limits. A mismatch records an error and leaves the next
entry unconsumed. An accepted entry is consumed even if its output later fails
validation or exceeds the output cap. No retries occur implicitly.

Each `complete` call appends one immutable result to the provider's `attempts`
tuple view, including rejected requests, mismatches, source errors and exhaustion.
Invalid requests have `request=None`; their untrusted raw input is deliberately
not retained. Indices count all attempts. Attempts are in-memory source records,
not durable audit receipts, and callers must persist them through an admitted
future boundary if required. A rejected oversized/invalid response becomes an
error result; its complete original result is retained in detached
`rejected_response_json`, including original source errors, usage and costs, but
it is never an accepted action. Rejected-response metadata is internal evidence,
not part of the accepted output byte envelope.

Current offline execution uses `Cost('known_zero')`. This says nothing about
original source generation cost: replay `source_cost` is separate and defaults to
unknown. `Cost('known', amount_decimal='0.01', currency='USD')` is a supplied
source record, not verified billing. Raw token usage is never fabricated.

`LedgerStub` is NON-ADMITTED and non-durable. `reserve(request_id, *, mode)`,
`record(result, *, mode)` and `summarize(*, mode)` allow only authored_mock and
strict_replay. Every live/unknown mode is refused, including summarize. This
stub has no pricing, budget admission, restart durability or dynamic evidence
claim and does not substitute for S3 or any paid accounting qualification.
# Public action-loop seam

## Offline broker and inherited-pipe codec source (r4)

OfflineBroker(provider,*,model_id,profile,limits,expected_requests=(),codec=BrokerCodec(),
max_requests=16) owns fixed built-in AuthoredMockProvider or ReplayProvider configuration.
profile must exactly match authored_mock/strict_replay. Live, custom/plugin and
unconfigured providers are refused. Worker data cannot choose a model, endpoint,
provider path, handler, schema or limits. This module opens no pipe/process/network.

Operator-only authorize_request(ProviderRequest) installs an immutable expected
request made from an actual PUBLIC observation and externally cleared prompt.
It verifies fixed model/limits/schema and rejects duplicate IDs. This method and
the broker/provider objects MUST NOT be exported to the worker. The worker may
call only handle(mapping), or handle_frame(bytes) through the future D1 transport.
Without a trusted unused binding, dispatch fails closed; a worker-supplied hash
alone never establishes an authentic observation or approved prompt.

The worker request has exactly version=rlab.offline.request.v1, request_id,
observation_digest, schema_sha256, messages. Schema digest is SHA256 of canonical
action_schema(); messages are ordinary closed role/content objects. Broker builds
the ProviderRequest using its own model/schema/limits, then compares the complete
record to the trusted binding. Binding is consumed before its single provider
call, including thrown/unknown outcomes; no automatic retry is possible.

Response has version=rlab.offline.response.v1, request_id, observation_digest,
request_binding_sha256, schema_sha256, profile, model_id, ok, result, error.
Unavailable identity/binding is null, never manufactured. Result contains action,
error, raw_usage, usage_state, provider_request_id, actual_model_id, timings,
current_cost, source_cost, mode, attempt_index, rejected_response_sha256. Actions
omit absent fields. Broker independently applies output/wait limits. Provider
errors keep their result; broker rejection/unknown exceptions have null result.
Missing result/usage/timing/cost is unknown, not proof of zero or success. Current
valid offline ProviderResult cost is known_zero; replay source cost stays separate.
Operator attempts retain full immutable ProviderResult even when wire output is
too large; the worker receives a bounded error and optional rejection digest.
Returned dictionaries are detached from retained canonical operator records.

BrokerCodec encodes canonical UTF-8 JSON with a four-byte unsigned big-endian
body length. Default body cap262144 bytes; operator-configurable8192..1048576.
decode requires exactly one complete frame, matching length, canonical object,
no duplicate keys, noninteger/nonfinite numbers or trailing data. It performs no
I/O. Future D1 pipe code must check the prefix cap BEFORE allocating/reading its
body, assemble one bounded frame and stop on closure. Invalid/malformed frames
count toward the same max_requests cap as valid calls. Once closed, BrokerClosed
refuses further acceptance; transport must stop reading, not loop on rejections.

BrokerAttempt records accepted calls/errors as canonical request/response plus
optional original ProviderResult and bounded bad-frame digest. Oversized raw
frames have no content digest, explicitly unknown. Operator configuration and
request table are bounded; source assumes one serialized owner. No authentication,
actual inherited-pipe isolation, admission, timing, worker denial or durable paid
accounting is established. LedgerStub remains non-durable and live-refusing. The
action/supervisor owner supplies authority-clock deadlines and hard preemption;
broker forwards only existing provider timing and invents no authority timestamps.

## Original prompt profiles and clearance source (r4)

BASE_PROMPT_PROFILE and RP_PROMPT_PROFILE are original local wording. RP uses the
refresh-on-transient-error method described in the adopted plan; it copies no
WAREX text and is not a benchmark reproduction or licence-admission claim. Base
R0/R1/R2/R3/R23 shares one instruction without history/reconciliation/semantic
wrapper logic. RP adds refresh-on-error only. No private schedules/answers or
family-specific instructions enter messages. Schema and caller caps are equal.

PromptProfile.descriptor_json/digest bind wording, public message contract,
eligibility and action schema. select_prompt_profile(arm,source_kind,stage,
cleared_prompt_profiles=...) requires operator-retained EXTERNALLY cleared exact
hashes; source computes hashes but never self-clears them. RP eligibility is only
(mock,mock), (mock,pilot), (live,pilot); unavailable/main/heldout combinations remain
not_executed with the requested arm retained. Other live labels do not enable any
live transport. Actual model/access/licence/research gates are separate and pending.

run_offline adds keyword args arm='R0', source_kind='mock', stage='mock',
cleared_prompt_profiles=None. Old call syntax remains valid; absent clearance now
returns LoopResult('not_executed',0,0,...) BEFORE clock/observation/provider access.
D1/D3 must forward actual trusted clearance; never substitute an arm or derive
clearance from a worker claim. D3 preserves its scheduled row as not_executed,
not an omitted arm or measured clean result. render_prompt_messages returns a
fresh detached tuple of role/content dicts; ProviderRequest stores immutable
canonical JSON. Public caps/feedback are included identically across arms and
oversized requests are rejected without truncation. No profile, loop, broker,
codec, mock or replay has been executed in this construction phase.

Committed D1 interface reconciliation (1898202): provider Action.operation is
explicitly mapped to rlab.actions.Action.kind by rlab.agents.map_action(). Fields
are selected, not passed as an unchecked raw tool dictionary. The D1 closed parser
and validate_action enforce their stricter ref160/path512/wait3000 limits; provider
limits may be wider, so unsupported values are rejected without clamping.
Click requires a caller-supplied ORIGINAL PUBLIC rlab.actions.Mutation. No mutation
intent is guessed from the reference or generated from private expected effects.
rlab.agents.observation_from_snapshot() uses D1 validate_snapshot and serializes
ordinary body/targets/url/served_version into a detached PublicObservation.

BrowserSession.observe() returns Snapshot with no caller deadline argument;
BrowserSession.act(Action,arm) does not accept the loop request ID/deadline. Thus
it is NOT assumed to implement ActionPort directly. D1's trusted backend must
forward the exact caller request ID, absolute authority-clock deadline and bound
receipt metadata, rather than manufacture ActionFeedback from client timing.
The mapping module delays D1 imports until called so existing offline records
remain importable on the older base; actual mapping requires the D1 source merge.
No browser/loop execution or joined compatibility is claimed.

`rlab.agents.run_offline(provider, port, *, model_id, provider_limits=Limits(),
limits=LoopLimits(), request_id_factory=None) -> LoopResult` consumes these offline
ports only. `LoopLimits` caps steps at40, model calls at16 and authority-clock
budget at180 seconds; callers can lower caps. Observations and issued actions
consume steps; every provider invocation consumes a model-call slot. Ordinary
failed/unknown action receipts are passed back to the actor; no implicit retry
occurs, even if a ProviderError says retryable.

D1 supplies an `ActionPort` with clock_id, now_ns(), observe(deadline_ns) and
execute(Action, *, request_id, deadline_ns). observe returns immutable
`PublicObservation(run_id,epoch,clock_id,goal,snapshot_epoch,snapshot_json,
allowed_paths)`. Snapshot is canonical detached public JSON, with no private spec,
authority controls or fault schedule. Allowed paths stay in the current public
task namespace or /history; the executor still owns route/method/worker isolation.
execute returns `ActionFeedback(request_id,run_id,epoch,clock_id,response_ns,
status,public_message='')`, with status acknowledged/failed/unknown.

The loop binds response request/model/schema/observation to its exact expected
request, rejects targeted actions from another captured snapshot and navigation
outside the trusted allowlist, and retains provider/port errors as immutable
LoopStep records. It adds no role/name/row semantic identity guard to R0/R1.
The public loop independently enforces returned offline mode, output byte cap
and wait cap even for a structural ProviderPort implementation; it does not rely
on built-in mocks to enforce the dispatch boundary. Rejected responses remain in
their LoopStep with source cost/usage intact. Initial clock failures are retained
as harness_unknown with no action or provider invocation.
D1's action/executor adapter owns actual DOM effects, recovery policy selection,
literal fill/select handling, lineage/accounting and public receipt capture.
No raw code/JS/shell/direct HTTP tool enters this loop.

`LoopResult.termination='finished'` means the actor chose finish, not that a goal
or server effect succeeded. A scorer must use the sealed evidence separately.
Harness failures/cap/deadline/provider errors remain named outcomes. A replay
caller can inject the exact trusted recorded request-ID stream, but observation,
schema, messages, model and limits binding are never relaxed to force a match.
An in-process function cannot forcibly preempt a blocking provider/action call;
trusted adapter/broker process timeouts remain later runtime qualification. This
package has no live provider or hard process boundary.

Source-only current construction: no loop, authored mock, replay, browser or
provider call has run. CLI and ActionPort bridge conformance, caps/clock/deadline,
malformed result/replay rejection, original/source-cost separation, actual worker
denial and independent admission remain deferred. No placeholder key is used.
