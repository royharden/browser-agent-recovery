"""Standalone offline facade entrypoint; later CLI may call evaluation.report.

Future invocation only; not executed during Dirty construction. Inputs contain
private expected specifications. Output remains operator-private by default.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.freeze import canonical, load_json
from evaluation.report import build_report, report_html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", type=Path, help="JSON: schedule, records, config, price, pins")
    parser.add_argument("output", type=Path, help="new private output directory; must not exist")
    args = parser.parse_args()
    raw = load_json(args.inputs.read_text(encoding="utf-8"))
    if set(raw) != {"schedule", "records", "config", "price", "pins"}:
        raise ValueError("closed report input fields required")
    report = build_report(raw["schedule"], raw["records"], config=raw["config"],
                          price=raw["price"], pins=raw["pins"])
    markup = report_html(report)
    args.output.mkdir(parents=False, exist_ok=False)
    (args.output / "report.json").write_text(canonical(report)+"\n", encoding="utf-8")
    (args.output / "index.html").write_text(markup, encoding="utf-8")


if __name__ == "__main__":
    main()
