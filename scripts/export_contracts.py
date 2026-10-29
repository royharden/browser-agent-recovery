"""Later-activation exporter. Do not run during Dirty Mode construction.

Requires the reviewed package on the trusted Python path. No arbitrary module or
type names are accepted. Output is stdout, for explicit operator redirection.
"""
import argparse
import json
from pathlib import Path

from rlab.public_schema import UnsupportedShape, public_schema


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        bundle = public_schema(args.checkout)
    except (OSError, SyntaxError, UnsupportedShape) as exc:
        parser.exit(2, f"contract export refused: {exc}\n")
    print(json.dumps(bundle, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
