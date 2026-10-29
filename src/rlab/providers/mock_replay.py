"""Authored offline responses and exact-bound replay, with every attempt retained."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Mapping, Sequence

from .port import (
    Action, Cost, Limits, ProviderError, ProviderRequest, ProviderResult,
    canonical, make_request, parse_action,
)


@dataclass(frozen=True)
class ReplayEntry:
    request: ProviderRequest
    action: Action | None = None
    error: ProviderError | None = None
    raw_usage_json: str | None = None
    provider_request_id: str | None = None
    actual_model_id: str | None = None
    source_cost: Cost = Cost("unknown")

    def __post_init__(self) -> None:
        if type(self.request) is not ProviderRequest:
            raise ValueError("replay requires a frozen ProviderRequest")
        # Reuse closed record validation without dispatching or importing an app.
        ProviderResult(self.request, self.action, self.error, self.raw_usage_json,
                       self.provider_request_id, self.actual_model_id,
                       source_cost=self.source_cost, mode="strict_replay")


class _OfflineProvider:
    mode = "authored_mock"

    def __init__(self) -> None:
        self._attempts: list[ProviderResult] = []

    @property
    def attempts(self) -> tuple[ProviderResult, ...]:
        return tuple(self._attempts)

    def complete(self, messages: Sequence[Mapping[str, str]], action_schema: Mapping[str, object],
                 model_id: str, limits: Limits, *, request_id: str,
                 observation_digest: str) -> ProviderResult:
        request = None
        candidate = None
        try:
            request = make_request(messages, action_schema, model_id, limits,
                                   request_id=request_id, observation_digest=observation_digest)
            result = self._next(request)
            candidate = result
            if result.action is not None:
                parse_action(result.action)
                if result.action.duration_ms is not None and result.action.duration_ms > limits.max_wait_ms:
                    raise ValueError("action wait exceeds request cap")
            payload = {"action": None if result.action is None else asdict(result.action),
                       "error": None if result.error is None else asdict(result.error),
                       "raw_usage": result.raw_usage}
            if len(canonical(payload).encode("utf-8")) > limits.max_output_bytes:
                result = self._error(request, "output_limit", "Offline response exceeds output byte cap")
                result = replace(result, rejected_response_json=canonical(asdict(candidate)),
                                 source_cost=candidate.source_cost)
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            # Fixed text prevents unbounded or sensitive caller values entering diagnostics.
            result = self._error(request, "invalid_request_or_action", "Request or action failed closed validation")
            if candidate is not None:
                result = replace(result, rejected_response_json=canonical(asdict(candidate)),
                                 source_cost=candidate.source_cost)
        self._attempts.append(result)
        return result

    def _error(self, request: ProviderRequest | None, code: str, message: str) -> ProviderResult:
        return ProviderResult(request, None, ProviderError(code, message),
                              attempt_index=len(self._attempts), mode=self.mode)

    def _next(self, request: ProviderRequest) -> ProviderResult:
        raise NotImplementedError


class AuthoredMockProvider(_OfflineProvider):
    """Consumes explicitly authored actions/errors; never a recorded model response."""

    def __init__(self, responses: Sequence[Action | ProviderError]) -> None:
        super().__init__()
        if type(responses) not in (tuple, list) or len(responses) > 10000:
            raise ValueError("bounded authored response sequence required")
        if any(type(item) not in (Action, ProviderError) for item in responses):
            raise ValueError("authored responses require closed records")
        self._responses = tuple(responses)
        self._position = 0

    def _next(self, request: ProviderRequest) -> ProviderResult:
        if self._position >= len(self._responses):
            return self._error(request, "authored_exhausted", "No authored response remains")
        response = self._responses[self._position]
        self._position += 1
        return ProviderResult(request, response if type(response) is Action else None,
                              response if type(response) is ProviderError else None,
                              attempt_index=len(self._attempts), mode=self.mode)


class ReplayProvider(_OfflineProvider):
    """Ordered replay requires exact canonical request equality, including limits."""
    mode = "strict_replay"

    def __init__(self, entries: Sequence[ReplayEntry]) -> None:
        super().__init__()
        if type(entries) not in (tuple, list) or len(entries) > 10000:
            raise ValueError("bounded replay sequence required")
        if any(type(entry) is not ReplayEntry for entry in entries):
            raise ValueError("ReplayEntry records required")
        self._entries = tuple(entries)
        self._position = 0

    def _next(self, request: ProviderRequest) -> ProviderResult:
        if self._position >= len(self._entries):
            return self._error(request, "replay_exhausted", "No replay entry remains")
        entry = self._entries[self._position]
        if request != entry.request:
            return self._error(request, "replay_binding_mismatch", "Replay request identity does not match")
        self._position += 1
        return ProviderResult(request, entry.action, entry.error, entry.raw_usage_json,
                              entry.provider_request_id, entry.actual_model_id,
                              source_cost=entry.source_cost,
                              attempt_index=len(self._attempts), mode=self.mode)


class LedgerStub:
    """NON-ADMITTED offline bookkeeping only. Not S3 accounting or a budget gate."""
    admitted = False

    def __init__(self) -> None:
        self._records: list[tuple[str, str]] = []

    @staticmethod
    def _offline(mode: str) -> None:
        if type(mode) is not str or mode not in ("authored_mock", "strict_replay"):
            raise ValueError("LedgerStub refuses all live or unknown requests")

    def reserve(self, request_id: str, *, mode: str) -> str:
        self._offline(mode)
        if type(request_id) is not str or not request_id or len(request_id) > 256:
            raise ValueError("invalid offline request ID")
        self._records.append(("reserve", request_id))
        return request_id

    def record(self, result: ProviderResult, *, mode: str) -> None:
        self._offline(mode)
        if type(result) is not ProviderResult or result.mode != mode:
            raise ValueError("offline result/mode mismatch")
        self._records.append(("record", canonical(asdict(result))))

    def summarize(self, *, mode: str) -> dict[str, object]:
        self._offline(mode)
        return {"admitted": False, "durable": False, "scope": "offline_only",
                "current_cost": "known_zero", "records": tuple(self._records)}
