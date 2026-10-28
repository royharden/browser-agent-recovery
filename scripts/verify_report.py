"""Standalone recomputation against an independently retained anchor file."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.freeze import load_json
from evaluation.report import verify_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("anchors", type=Path, help="external JSON pins and inputs_sha256")
    args = parser.parse_args()
    report = load_json(args.report.read_text(encoding="utf-8"))
    anchors = load_json(args.anchors.read_text(encoding="utf-8"))
    if set(anchors) != {"pins", "inputs_sha256"}:
        raise ValueError("closed external anchors required")
    verify_report(report, expected_pins=anchors["pins"],
                  expected_inputs_sha256=anchors["inputs_sha256"])
    print("Report recomputation matches supplied anchors; qualification remains separate.")


if __name__ == "__main__":
    main()
