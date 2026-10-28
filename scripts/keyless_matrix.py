"""Private optional matrix operator entrypoint; no backend auto-discovery.

Future use only. JSON admission is retained as unverified provenance; only a
trusted verifier integration may return VerifiedAdmission(PASS). No dispatch is
available from this standalone entrypoint until that integration is supplied.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import signal
import sys
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.freeze import canonical, digest, load_json
from evaluation.matrix_runner import MatrixRunPort, VerifiedAdmission, run_matrix, validate_inputs

MAX_INPUT_BYTES = 32 * 1024 * 1024


def _json(path: Path) -> dict:
    if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("bounded external JSON file required")
    value = load_json(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def _external(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    root = Path(__file__).resolve().parents[1]
    if resolved == root or root in resolved.parents:
        raise ValueError("operator inputs/output parent must be outside product source tree")
    return resolved


def main(argv: list[str] | None = None, *, port: MatrixRunPort | None = None,
         verifier: Callable[[dict, dict, str], VerifiedAdmission] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True,
                        help="private matrix/specs/config/price/pins/limits/entrypoint_sha256 JSON")
    parser.add_argument("--admission", type=Path, required=True,
                        help="external admission document; JSON PASS alone never suffices")
    parser.add_argument("--anchors", type=Path, required=True,
                        help="trusted external pins/input_sha256/admission_sha256 JSON")
    parser.add_argument("--output", type=Path, required=True,
                        help="new exclusive file in existing private directory outside repo")
    args = parser.parse_args(argv)
    inputs = validate_inputs(_json(_external(args.inputs)))
    document = _json(_external(args.admission))
    anchors = _json(_external(args.anchors))
    if (set(anchors) != {"pins", "input_sha256", "admission_sha256"}
            or anchors["pins"] != inputs["pins"] or anchors["input_sha256"] != digest(inputs)
            or anchors["admission_sha256"] != digest(document)):
        raise ValueError("external matrix/admission/source anchor mismatch")
    decision = None
    if document.get("state") == "FAIL":
        decision = VerifiedAdmission("FAIL", digest(inputs), ("external document FAIL: skip all",))
    elif verifier is not None:
        decision = verifier(document, anchors, digest(inputs))
        if not isinstance(decision, VerifiedAdmission):
            raise ValueError("trusted verifier must supply a typed decision")
    parent = _external(args.output.parent)
    # Resolve the parent but preserve exclusive creation of the final leaf;
    # x mode rejects existing symlinks too. ACLs/parent races need later probes.
    if not parent.is_dir() or args.output.name in {"", ".", ".."}:
        raise ValueError("existing operator-private parent and plain output name required")
    if any(c in args.output.name for c in '/\\:<>"|?*') or args.output.name.endswith((".", " ")):
        raise ValueError("plain output filename required")
    output = parent / args.output.name
    # Reserve output BEFORE potential dispatch so a preexisting artifact cannot
    # cause execution with nowhere to retain its receipt. Preserve partial file.
    with output.open("x", encoding="utf-8") as handle:
        stopping = False

        def request_stop(signum, frame):
            nonlocal stopping
            stopping = True

        previous = signal.signal(signal.SIGINT, request_stop)
        try:
            result = run_matrix(inputs, admission=decision, port=port, stop=lambda: stopping)
            handle.write(canonical(result) + "\n")
        finally:
            signal.signal(signal.SIGINT, previous)
    # The operator retains these OUTSIDE the artifact as selected verification
    # anchors. Printing them is not signature/custody or research acceptance.
    print(canonical({"envelope_sha256": result["sha256"],
                     "provenance_sha256": result["provenance_sha256"],
                     "qualification": "runtime_unverified; private artifact"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
