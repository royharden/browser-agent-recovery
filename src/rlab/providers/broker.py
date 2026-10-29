"""Operator-configured OFFLINE broker. No SDK, endpoint, plugin or transport.

Only handle/handle_frame are future worker entrypoints. authorize_request is an
operator-only method and MUST NOT be exposed over worker dispatch. This source
binds records; it does not qualify process isolation, signatures or hard timeouts.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import re

from .codec import BrokerCodec
from .mock_replay import AuthoredMockProvider, ReplayProvider
from .port import (Limits, ProviderRequest, ProviderResult, action_schema,
                   canonical, make_request, parse_action)

REQUEST_VERSION = "rlab.offline.request.v1"
RESPONSE_VERSION = "rlab.offline.response.v1"
REQUEST_FIELDS = {"version", "request_id", "observation_digest", "schema_sha256", "messages"}


def _sha(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _identity(value: object) -> str | None:
    if (type(value) is str and 1 <= len(value) <= 256
            and all(ord(char) >= 32 for char in value)):
        return value
    return None


class BrokerClosed(RuntimeError):
    """No more frames accepted. The future transport must stop reading."""


@dataclass(frozen=True)
class BrokerAttempt:
    index: int
    request_json: str | None
    response_json: str
    provider_result: ProviderResult | None
    wire_sha256: str | None = None


class OfflineBroker:
    def __init__(self, provider: AuthoredMockProvider | ReplayProvider, *, model_id: str,
                 profile: str, limits: Limits, expected_requests: tuple[ProviderRequest, ...] = (),
                 codec: BrokerCodec = BrokerCodec(), max_requests: int = 16):
        if type(provider) not in {AuthoredMockProvider, ReplayProvider}:
            raise ValueError("only built-in offline providers may be configured")
        if profile not in {"authored_mock", "strict_replay"} or provider.mode != profile:
            raise ValueError("live/unconfigured/mismatched profile refused")
        if _identity(model_id) is None or type(limits) is not Limits or type(codec) is not BrokerCodec:
            raise ValueError("fixed model, closed limits and codec required")
        if type(max_requests) is not int or not 1 <= max_requests <= 10000:
            raise ValueError("bounded operator request cap required")
        if type(expected_requests) is not tuple or len(expected_requests) > max_requests:
            raise ValueError("bounded trusted request tuple required")
        self._provider, self._model_id, self._profile = provider, model_id, profile
        self._limits, self._codec, self._max_requests = limits, codec, max_requests
        self._requests: dict[str, ProviderRequest] = {}
        self._consumed: set[str] = set()
        self._attempts: list[BrokerAttempt] = []
        self._schema_sha256 = hashlib.sha256(canonical(action_schema()).encode()).hexdigest()
        for request in expected_requests:
            self.authorize_request(request)

    @property
    def attempts(self) -> tuple[BrokerAttempt, ...]:
        return tuple(self._attempts)

    @property
    def closed(self) -> bool:
        return len(self._attempts) >= self._max_requests

    def _open(self) -> None:
        if self.closed:
            raise BrokerClosed("offline broker accepted-request cap exhausted")

    def authorize_request(self, request: ProviderRequest) -> None:
        """OPERATOR ONLY: bind actual public observation and cleared messages.

        Worker claims never populate this table. A missing trusted binding is a
        rejection, not permission to trust a worker's observation hash or schema.
        The operator must build these messages from its cleared public profile.
        """
        self._open()
        if type(request) is not ProviderRequest or request.model_id != self._model_id or request.limits != self._limits:
            raise ValueError("trusted request does not match fixed broker configuration")
        rebuilt = make_request(json.loads(request.messages_json), json.loads(request.action_schema_json),
                               self._model_id, self._limits, request_id=request.request_id,
                               observation_digest=request.observation_digest)
        if rebuilt != request or request.request_id in self._requests:
            raise ValueError("invalid/duplicate trusted request binding")
        if len(self._requests) >= self._max_requests:
            raise ValueError("trusted request table cap")
        self._requests[request.request_id] = request

    def _envelope(self, request_id: str | None, observation: str | None,
                  binding: str | None, *, result: dict | None = None,
                  code: str | None = None, message: str = "") -> dict:
        error = None if code is None else {"code": code, "message": message, "retryable": False}
        return {"version": RESPONSE_VERSION, "request_id": request_id,
                "observation_digest": observation, "request_binding_sha256": binding,
                "schema_sha256": self._schema_sha256, "profile": self._profile,
                "model_id": self._model_id, "ok": code is None,
                "result": result, "error": error}

    def _retain(self, raw: str | None, response: dict, result: ProviderResult | None,
                *, wire_sha256: str | None = None) -> dict:
        try:
            self._codec.encode(response)
        except (ValueError, TypeError, RecursionError, UnicodeError, OverflowError):
            response = self._envelope(response["request_id"], response["observation_digest"],
                                      response["request_binding_sha256"], code="response_limit",
                                      message="Response exceeds configured wire cap; operator retains result")
        encoded = canonical(response)
        self._attempts.append(BrokerAttempt(len(self._attempts), raw, encoded, result, wire_sha256))
        return json.loads(encoded)  # detached from retained operator record

    @staticmethod
    def _result_payload(result: ProviderResult) -> dict:
        return {"action": None if result.action is None else {
                    key: value for key, value in asdict(result.action).items() if value is not None},
                "error": None if result.error is None else asdict(result.error),
                "raw_usage": result.raw_usage, "usage_state": result.usage_state,
                "provider_request_id": result.provider_request_id,
                "actual_model_id": result.actual_model_id, "timings": result.timings,
                "current_cost": asdict(result.current_cost),
                "source_cost": None if result.source_cost is None else asdict(result.source_cost),
                "mode": result.mode, "attempt_index": result.attempt_index,
                "rejected_response_sha256": None if result.rejected_response_json is None else
                    hashlib.sha256(result.rejected_response_json.encode()).hexdigest()}

    def handle(self, request_mapping: dict) -> dict:
        self._open()
        raw = None
        request_id = observation = binding = None
        returned = None
        try:
            # The codec cap applies to direct callers too; no worker-owned object
            # remains referenced after canonical detachment.
            frame = self._codec.encode(request_mapping)
            raw = frame[4:].decode("utf-8")
            request = json.loads(raw)
            request_id = _identity(request.get("request_id"))
            observation = request.get("observation_digest") if _sha(request.get("observation_digest")) else None
            if set(request) != REQUEST_FIELDS or request["version"] != REQUEST_VERSION:
                return self._retain(raw, self._envelope(request_id, observation, None,
                    code="invalid_request", message="Closed versioned worker request required"), None)
            if request_id is None or observation is None or request["schema_sha256"] != self._schema_sha256:
                return self._retain(raw, self._envelope(request_id, observation, None,
                    code="binding_mismatch", message="Request identity, observation or schema rejected"), None)
            expected = self._requests.get(request_id)
            if expected is None or request_id in self._consumed:
                return self._retain(raw, self._envelope(request_id, observation, None,
                    code="request_not_authorized", message="Trusted unused request binding required"), None)
            actual = make_request(request["messages"], action_schema(), self._model_id, self._limits,
                                  request_id=request_id, observation_digest=observation)
            if actual != expected:
                return self._retain(raw, self._envelope(request_id, observation, None,
                    code="binding_mismatch", message="Public messages/observation do not match trusted binding"), None)
            binding = expected.binding_digest
            self._consumed.add(request_id)  # no implicit retry, including thrown/unknown result
            returned = self._provider.complete(request["messages"], action_schema(), self._model_id,
                                               self._limits, request_id=request_id,
                                               observation_digest=observation)
            if type(returned) is not ProviderResult or returned.request != expected or returned.mode != self._profile:
                raise ValueError("unbound offline provider response")
            if returned.action is not None:
                action = parse_action(returned.action)
                if action.duration_ms is not None and action.duration_ms > self._limits.max_wait_ms:
                    raise ValueError("returned wait exceeds fixed profile")
            bounded = {"action": None if returned.action is None else asdict(returned.action),
                       "error": None if returned.error is None else asdict(returned.error),
                       "raw_usage": returned.raw_usage}
            if len(canonical(bounded).encode()) > self._limits.max_output_bytes:
                raise ValueError("returned response exceeds fixed profile")
            payload = self._result_payload(returned)
            response = self._envelope(request_id, observation, binding, result=payload,
                code="provider_error" if returned.error is not None else None,
                message="Offline provider returned an error" if returned.error is not None else "")
            return self._retain(raw, response, returned)
        except Exception:
            return self._retain(raw, self._envelope(request_id, observation, binding,
                code="offline_request_failed", message="Offline request failed closed; no automatic retry"),
                returned if type(returned) is ProviderResult else None)

    def handle_frame(self, frame: bytes) -> bytes:
        """Pure byte facade. The D1 owner supplies real inherited-pipe I/O later."""
        self._open()
        try:
            request = self._codec.decode(frame)
        except Exception:
            wire = (hashlib.sha256(frame).hexdigest() if type(frame) is bytes
                    and len(frame) <= self._codec.max_frame_bytes+4 else None)
            response = self._retain(None, self._envelope(None, None, None, code="bad_frame",
                message="Malformed/oversized frame refused before dispatch"), None, wire_sha256=wire)
        else:
            response = self.handle(request)
        return self._codec.encode(response)
