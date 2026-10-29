"""Original, model-neutral offline contracts. No transport or browser authority."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Mapping, Protocol, Sequence
from urllib.parse import unquote, urlsplit


def canonical(value: object) -> str:
    """Detach JSON data; reject non-JSON values, NaN and non-string object keys."""
    def check(item: object) -> None:
        if item is None or type(item) in (str, int, bool):
            return
        if type(item) is list or type(item) is tuple:
            for child in item:
                check(child)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                check(child)
            return
        raise ValueError("only finite integer/string/bool/null JSON data is supported")
    check(value)
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _text(value: object, name: str, maximum: int = 256) -> None:
    if type(value) is not str or not value or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError(f"invalid {name}")


@dataclass(frozen=True)
class Limits:
    max_messages: int = 64
    max_input_bytes: int = 65536
    max_output_bytes: int = 8192
    deadline_ms: int = 30000
    max_wait_ms: int = 5000

    def __post_init__(self) -> None:
        ceilings = (256, 1048576, 65536, 300000, 10000)
        for value, ceiling in zip(asdict(self).values(), ceilings):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("limits must be positive bounded integers")
        if self.max_wait_ms > self.deadline_ms:
            raise ValueError("wait cap exceeds deadline shape")


@dataclass(frozen=True)
class Action:
    operation: str
    ref: str | None = None
    snapshot_epoch: str | None = None
    value: str | None = None
    path: str | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        required = {
            "click": {"ref", "snapshot_epoch"},
            "fill": {"ref", "snapshot_epoch", "value"},
            "select": {"ref", "snapshot_epoch", "value"},
            "goto": {"path"}, "back": set(), "reload": set(),
            "wait": {"duration_ms"}, "finish": set(),
        }
        if type(self.operation) is not str or self.operation not in required:
            raise ValueError("unknown action operation")
        values = asdict(self)
        populated = {key for key, value in values.items() if key != "operation" and value is not None}
        if populated != required[self.operation]:
            raise ValueError("action has missing or forbidden fields")
        for key in ("ref", "snapshot_epoch"):
            if values[key] is not None:
                _text(values[key], key)
        if self.value is not None and (type(self.value) is not str or len(self.value.encode("utf-8")) > 4096):
            raise ValueError("invalid action value")
        if self.path is not None:
            _text(self.path, "path", 2048)
            decoded = self.path
            # Reject encoded delimiters/traversal too; ambiguous normalization is refused.
            for _ in range(3):
                next_path = unquote(decoded)
                if next_path == decoded:
                    break
                decoded = next_path
            parts = urlsplit(decoded)
            if (not decoded.startswith("/") or decoded.startswith("//") or "\\" in decoded
                    or "%" in decoded or parts.scheme or parts.netloc or parts.query or parts.fragment
                    or any(segment in (".", "..") for segment in decoded.split("/"))
                    or any(ord(c) < 33 or ord(c) == 127 for c in decoded)):
                raise ValueError("goto requires an unambiguous local absolute path")
        if self.duration_ms is not None and (type(self.duration_ms) is not int or not 1 <= self.duration_ms <= 10000):
            raise ValueError("wait must be between 1 and 10000 milliseconds")


def action_schema() -> dict[str, object]:
    """Return a fresh versioned closed schema; arbitrary caller schemas are refused."""
    strings = {"type": "string", "minLength": 1, "maxLength": 256}
    variants = []
    for operation, fields in (
        ("click", ("ref", "snapshot_epoch")),
        ("fill", ("ref", "snapshot_epoch", "value")),
        ("select", ("ref", "snapshot_epoch", "value")),
        ("goto", ("path",)), ("back", ()), ("reload", ()),
        ("wait", ("duration_ms",)), ("finish", ()),
    ):
        properties: dict[str, object] = {"operation": {"const": operation}}
        for field in fields:
            properties[field] = dict(strings)
        if "value" in fields:
            properties["value"] = {"type": "string", "maxLength": 4096}
        if "path" in fields:
            properties["path"] = {"type": "string", "minLength": 1, "maxLength": 2048}
        if "duration_ms" in fields:
            properties["duration_ms"] = {"type": "integer", "minimum": 1, "maximum": 10000}
        variants.append({"type": "object", "additionalProperties": False,
                         "required": ["operation", *fields], "properties": properties})
    return {"$id": "rlab.offline.action.v1", "oneOf": variants}


def parse_action(value: Mapping[str, object] | Action) -> Action:
    if type(value) is Action:
        return Action(**asdict(value))
    if type(value) is not dict or any(key not in Action.__dataclass_fields__ for key in value):
        raise ValueError("action must contain only closed action fields")
    # Explicit null is not a legal wire field: absent fields stay absent.
    if any(item is None for item in value.values()):
        raise ValueError("null action fields are forbidden")
    try:
        return Action(**value)
    except TypeError as exc:
        raise ValueError("invalid action fields") from exc


@dataclass(frozen=True)
class Cost:
    state: str = "unknown"
    amount_decimal: str | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        if self.state not in ("unknown", "known_zero", "known"):
            raise ValueError("invalid cost state")
        if self.state != "known":
            if self.amount_decimal is not None or self.currency is not None:
                raise ValueError("non-numeric cost state cannot carry an amount")
        else:
            if type(self.amount_decimal) is not str or type(self.currency) is not str or not re.fullmatch(r"[A-Z]{3}", self.currency):
                raise ValueError("known source cost requires decimal text and currency")
            try:
                amount = Decimal(self.amount_decimal)
            except InvalidOperation as exc:
                raise ValueError("invalid source cost") from exc
            if not amount.is_finite() or amount < 0:
                raise ValueError("invalid source cost")


@dataclass(frozen=True)
class ProviderError:
    code: str
    message: str
    retryable: bool = False

    def __post_init__(self) -> None:
        _text(self.code, "error code", 64)
        _text(self.message, "error message", 1024)
        if type(self.retryable) is not bool:
            raise ValueError("retryable must be boolean")


@dataclass(frozen=True)
class ProviderRequest:
    messages_json: str
    action_schema_json: str
    model_id: str
    limits: Limits
    request_id: str
    observation_digest: str

    def __post_init__(self) -> None:
        if type(self.limits) is not Limits:
            raise ValueError("Limits record required")
        _text(self.model_id, "model_id")
        _text(self.request_id, "request_id")
        if type(self.observation_digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", self.observation_digest):
            raise ValueError("observation digest must be lowercase SHA-256 hex")
        if type(self.action_schema_json) is not str or self.action_schema_json != canonical(action_schema()):
            raise ValueError("unknown action schema")
        if type(self.messages_json) is not str:
            raise ValueError("canonical messages required")
        messages = json.loads(self.messages_json)
        if canonical(messages) != self.messages_json or type(messages) is not list or not 1 <= len(messages) <= self.limits.max_messages:
            raise ValueError("invalid canonical messages")
        for message in messages:
            if (type(message) is not dict or set(message) != {"role", "content"}
                    or message["role"] not in ("system", "user", "assistant")
                    or type(message["content"]) is not str):
                raise ValueError("messages require closed role/content strings")
        if len((self.messages_json + self.action_schema_json).encode("utf-8")) > self.limits.max_input_bytes:
            raise ValueError("request input exceeds byte cap")

    @property
    def binding_digest(self) -> str:
        return hashlib.sha256(canonical(asdict(self)).encode("utf-8")).hexdigest()


def make_request(messages: Sequence[Mapping[str, str]], schema: Mapping[str, object],
                 model_id: str, limits: Limits, *, request_id: str,
                 observation_digest: str) -> ProviderRequest:
    if type(limits) is not Limits or type(messages) not in (list, tuple):
        raise ValueError("bounded message sequence and Limits record required")
    if not 1 <= len(messages) <= limits.max_messages:
        raise ValueError("message count exceeds cap")
    if type(schema) is not dict or schema != action_schema():
        raise ValueError("unknown action schema")
    total = 0
    for message in messages:
        if type(message) is not dict or set(message) != {"role", "content"} or type(message["content"]) is not str:
            raise ValueError("closed message objects required")
        total += len(message["content"].encode("utf-8"))
        if total > limits.max_input_bytes:
            raise ValueError("message content exceeds byte cap")
    return ProviderRequest(canonical(messages), canonical(schema), model_id, limits,
                           request_id, observation_digest)


@dataclass(frozen=True)
class ProviderResult:
    request: ProviderRequest | None
    action: Action | None
    error: ProviderError | None
    raw_usage_json: str | None = None
    provider_request_id: str | None = None
    actual_model_id: str | None = None
    timings: tuple[tuple[str, int], ...] = ()
    current_cost: Cost = Cost("known_zero")
    source_cost: Cost | None = None
    attempt_index: int = 0
    mode: str = "authored_mock"
    rejected_response_json: str | None = None

    def __post_init__(self) -> None:
        if (self.action is None) == (self.error is None):
            raise ValueError("result requires exactly one action or error")
        if self.action is not None and type(self.action) is not Action:
            raise ValueError("Action record required")
        if self.error is not None and type(self.error) is not ProviderError:
            raise ValueError("ProviderError record required")
        if self.request is not None and type(self.request) is not ProviderRequest:
            raise ValueError("ProviderRequest record required")
        if self.raw_usage_json is not None:
            if type(self.raw_usage_json) is not str or canonical(json.loads(self.raw_usage_json)) != self.raw_usage_json:
                raise ValueError("raw usage must be canonical detached JSON")
        if self.rejected_response_json is not None:
            if (type(self.rejected_response_json) is not str
                    or canonical(json.loads(self.rejected_response_json)) != self.rejected_response_json):
                raise ValueError("rejected response must be canonical detached JSON")
        if self.mode not in ("authored_mock", "strict_replay") or type(self.attempt_index) is not int or self.attempt_index < 0:
            raise ValueError("invalid offline result provenance")
        if type(self.current_cost) is not Cost or self.current_cost != Cost("known_zero"):
            raise ValueError("current offline cost must be known_zero")
        if self.source_cost is not None and type(self.source_cost) is not Cost:
            raise ValueError("source Cost record required")
        if type(self.timings) is not tuple or any(type(item) is not tuple or len(item) != 2
                or type(item[0]) is not str or type(item[1]) is not int or item[1] < 0 for item in self.timings):
            raise ValueError("timings must be immutable nonnegative integer pairs")
        for name in ("provider_request_id", "actual_model_id"):
            value = getattr(self, name)
            if value is not None:
                _text(value, name)

    @property
    def raw_usage(self) -> object:
        """A fresh detached value; None means missing usage, never measured zero."""
        return None if self.raw_usage_json is None else json.loads(self.raw_usage_json)

    @property
    def usage_state(self) -> str:
        return "unknown" if self.raw_usage_json is None else "reported_unverified"


class ProviderPort(Protocol):
    mode: str

    def complete(self, messages: Sequence[Mapping[str, str]], action_schema: Mapping[str, object],
                 model_id: str, limits: Limits, *, request_id: str,
                 observation_digest: str) -> ProviderResult: ...

    @property
    def attempts(self) -> tuple[ProviderResult, ...]: ...
