"""Pure bounded length-prefixed JSON codec. Opens no pipe, file or process."""
from dataclasses import dataclass
import json

from .port import canonical


def _object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate wire key")
        result[key] = value
    return result


def _reject_number(value: str) -> None:
    raise ValueError("noninteger/nonfinite wire number")


@dataclass(frozen=True)
class BrokerCodec:
    max_frame_bytes: int = 262144  # JSON body; prefix is another four bytes

    def __post_init__(self) -> None:
        if type(self.max_frame_bytes) is not int or not 8192 <= self.max_frame_bytes <= 1048576:
            raise ValueError("bounded codec body cap must be 8192..1048576")

    def encode(self, message: dict) -> bytes:
        if type(message) is not dict:
            raise ValueError("wire object required")
        body = canonical(message).encode("utf-8")
        if not 1 <= len(body) <= self.max_frame_bytes:
            raise ValueError("wire body exceeds cap")
        return len(body).to_bytes(4, "big")+body

    def decode(self, frame: bytes) -> dict:
        if type(frame) is not bytes or len(frame) < 5 or len(frame) > self.max_frame_bytes+4:
            raise ValueError("invalid wire frame length")
        length = int.from_bytes(frame[:4], "big")
        if not 1 <= length <= self.max_frame_bytes or length != len(frame)-4:
            raise ValueError("wire length prefix mismatch")
        text = frame[4:].decode("utf-8")
        value = json.loads(text, object_pairs_hook=_object, parse_float=_reject_number,
                           parse_constant=_reject_number)
        if type(value) is not dict or canonical(value) != text:
            raise ValueError("canonical closed JSON object required")
        return value
