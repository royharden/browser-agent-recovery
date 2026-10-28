"""Bounded public action decoder; no authority/admin imports or executable tools.

This worker entry point refuses execution until a real public IPC transport joins
the trusted executor. Decoder construction is not a sandbox or live actor loop.
"""
import json
from typing import BinaryIO

from .actions import Action, parse_action

MAX_FRAME_BYTES = 16384
MAX_ACTIONS = 40


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def decode_action(frame: bytes) -> Action:
    if type(frame) is not bytes or not 0 < len(frame) <= MAX_FRAME_BYTES:
        raise ValueError("bounded public JSON frame required")
    try:
        value = json.loads(frame.decode("utf-8"), object_pairs_hook=_object,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("invalid public JSON") from exc
    return parse_action(value)


def read_action(stream: BinaryIO) -> Action:
    """Caller must provide a transport with enforced read deadline/preemption."""
    frame = stream.readline(MAX_FRAME_BYTES + 1)
    if not frame.endswith(b"\n"):
        raise ValueError("bounded newline-terminated frame required")
    return decode_action(frame)


def main() -> int:
    # No stdin loop without a bounded transport and fresh isolated context.
    raise RuntimeError("worker activation refused: public IPC, enforcement and browser context unjoined")


if __name__ == "__main__":
    raise SystemExit(main())
