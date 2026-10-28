"""Private operator CLI; fixed trusted seams, no actor/browser imports at startup."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Literal, Mapping, Protocol, Sequence

TASKS = (("F1", "order"), ("F2", "ticket"), ("F3", "delete"))
POLICIES = ("R0", "R1", "R2", "R3", "R23")
PIN_NAMES = frozenset(("source", "schedule", "oracle", "config", "price"))
SHA256 = re.compile(r"[0-9a-f]{64}")
MAX_JSON_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class FixtureRequest:
    """Public selection only; no expected answer or private specification."""
    task: Literal["F1", "F2", "F3"]
    policy: Literal["R0", "R1", "R2", "R3", "R23"]
    max_actions: int
    max_probes: int
    horizon_ns: int
    seed: int
    mode: Literal["fixture"] = "fixture"


@dataclass(frozen=True)
class PortResult:
    status: Literal["complete", "pending", "unavailable"]
    detail: str
    artifact: Mapping[str, Any] | None = None


class FixturePort(Protocol):
    """Trusted host owns orchestration through public actions and snapshots."""
    def run(self, request: FixtureRequest) -> PortResult: ...
    def matrix(self, request: FixtureRequest) -> PortResult: ...
    def freeze(self, request: FixtureRequest) -> PortResult: ...


class AdmissionPort(Protocol):
    def admit(self, manifest: Mapping[str, Any]) -> PortResult: ...


class ProviderPort(Protocol):
    """Future seam only; live CLI execution remains closed."""
    def readiness(self) -> PortResult: ...


@dataclass(frozen=True)
class OperatorPorts:
    fixture: FixturePort | None = None
    admission: AdmissionPort | None = None
    provider: ProviderPort | None = None


class UnavailableError(Exception):
    pass


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(value: str) -> Any:
    raise ValueError("non-finite JSON value")


def _json(path: Path) -> Any:
    if not path.is_file() or path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("JSON input must be a regular file of at most 16 MiB")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=_unique, parse_constant=_nonfinite)


def _mapping(path: Path) -> dict[str, Any]:
    value = _json(path)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return value


def _pins(path: Path) -> dict[str, str]:
    value = _mapping(path)
    if set(value) != PIN_NAMES or any(
        not isinstance(item, str) or SHA256.fullmatch(item) is None
        for item in value.values()
    ):
        raise ValueError("pins require source/schedule/oracle/config/price lowercase SHA256")
    return value


def _digest(path: Path) -> str:
    if not path.is_file() or path.stat().st_size > 256:
        raise ValueError("expected-inputs anchor must be a small SHA256 text file")
    value = path.read_text(encoding="ascii").strip()
    if SHA256.fullmatch(value) is None:
        raise ValueError("expected-inputs anchor must contain one lowercase SHA256")
    return value


def _evaluator() -> Any:
    # Fixed facade only: no artifact path added to sys.path, plugin or script loading.
    # evaluation is operator tooling deliberately excluded from the src wheel.
    try:
        return importlib.import_module("evaluation.report")
    except ModuleNotFoundError as exc:
        if exc.name in ("evaluation", "evaluation.report"):
            raise UnavailableError("operator evaluator evaluation.report is unavailable") from exc
        raise UnavailableError("operator evaluator has an unavailable dependency") from exc


def _private_output(directory: Path, name: str, text: str) -> Path:
    directory = directory.resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("private directory must already exist")
    product = Path(__file__).resolve().parents[2]
    if directory == product or product in directory.parents:
        raise ValueError("private artifacts must be outside the product source tree")
    if (not name or Path(name).name != name or name in (".", "..")
            or any(character in name for character in '/\\:<>"|?*')
            or name.endswith((".", " "))):
        raise ValueError("output name must be a plain filename")
    target = directory / name
    # Exclusive creation refuses existing files/symlinks. Directory ACLs are an
    # operator obligation: an output filename cannot establish private access.
    with target.open("x", encoding="utf-8") as handle:
        handle.write(text)
        handle.write("\n")
    return target


def _emit(status: str, detail: str, **extra: Any) -> None:
    print(json.dumps({
        "status": status, "detail": detail, "readiness": "unknown",
        "execution": "not_run", "validation": "runtime_unverified",
        "model_measurement": "not_yet_measured", **extra,
    }, sort_keys=True, allow_nan=False))


def _positive(value: str) -> int:
    number = int(value)
    if number < 1 or number > 180_000_000_000:
        raise argparse.ArgumentTypeError("value must be between 1 and 180000000000")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rlab", description="Private operator CLI; runtime unverified")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("tasks", help="list original public F1/F2/F3 development families")
    for name in ("run", "matrix", "freeze"):
        command = commands.add_parser(name)
        command.add_argument("--mode", choices=("fixture", "live"), default="fixture")
        command.add_argument("--task", choices=tuple(task[0] for task in TASKS), default="F1")
        command.add_argument("--policy", choices=POLICIES, default="R0")
        command.add_argument("--max-actions", type=_positive, default=40)
        command.add_argument("--max-probes", type=_positive, default=4)
        command.add_argument("--horizon-ns", type=_positive, default=180_000_000_000)
        command.add_argument("--seed", type=int, default=0)
        if name == "freeze":
            command.add_argument("--private-dir", required=True, type=Path)
            command.add_argument("--name", default="schedule.json")
    report = commands.add_parser("report", help="build private operator report using fixed evaluator")
    for name in ("schedule", "records", "pins", "config", "price"):
        report.add_argument(f"--{name}", required=True, type=Path)
    report.add_argument("--private-dir", required=True, type=Path)
    report.add_argument("--name", default="report.json")
    report.add_argument("--format", choices=("json", "html"), default="json")
    verify = commands.add_parser("verify-report")
    verify.add_argument("--report", required=True, type=Path)
    verify.add_argument("--trusted-pins", required=True, type=Path)
    verify.add_argument("--expected-inputs-sha256", required=True, type=Path)
    admit = commands.add_parser("admit")
    admit.add_argument("--manifest", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None, *, ports: OperatorPorts | None = None) -> int:
    """Trusted embedding may inject ports; command-line artifacts cannot load code."""
    args = _parser().parse_args(argv)
    ports = ports or OperatorPorts()
    try:
        if args.command == "tasks":
            _emit("available", "Original development families only", tasks=[
                {"id": identifier, "operation": operation} for identifier, operation in TASKS
            ])
            return 0
        if args.command in ("run", "matrix", "freeze"):
            if args.mode == "live":
                raise UnavailableError("live execution unavailable: provider/admission/worker integration pending")
            if (args.max_actions > 40 or args.max_probes > 40
                    or not 0 <= args.seed <= 999):
                raise ValueError("development action/probe caps or seed outside closed bounds")
            if ports.fixture is None:
                raise UnavailableError("fixture backend PENDING: trusted public action/snapshot host unavailable")
            request = FixtureRequest(
                args.task, args.policy, args.max_actions, args.max_probes, args.horizon_ns, args.seed
            )
            if args.command == "run":
                result = ports.fixture.run(request)
            elif args.command == "matrix":
                result = ports.fixture.matrix(request)
            else:
                result = ports.fixture.freeze(request)
            if result.status != "complete":
                _emit(result.status, result.detail)
                return 3
            if args.command == "freeze":
                if result.artifact is None:
                    raise ValueError("freeze returned no schedule artifact")
                path = _private_output(args.private_dir, args.name, json.dumps(
                    result.artifact, sort_keys=True, indent=2, allow_nan=False
                ))
                _emit("complete", result.detail, private_artifact=str(path))
            else:
                # Private backend payloads are never copied to actor/public output.
                _emit("complete", result.detail, execution="unknown")
            return 0
        if args.command == "admit":
            if ports.admission is None:
                raise UnavailableError("admission PENDING: trusted custodian admission backend unavailable")
            result = ports.admission.admit(_mapping(args.manifest))
            _emit(result.status, result.detail)
            return 0 if result.status == "complete" else 3
        if args.command == "verify-report":
            report_path = args.report.resolve(strict=True)
            anchors = (args.trusted_pins.resolve(strict=True), args.expected_inputs_sha256.resolve(strict=True))
            if report_path in anchors:
                raise ValueError("trust anchors must be separately selected files, not the report")
            expected_pins = _pins(anchors[0])
            expected_digest = _digest(anchors[1])
            verified = _evaluator().verify_report(
                _mapping(report_path), expected_pins=expected_pins,
                expected_inputs_sha256=expected_digest,
            )
            if verified is not True:
                raise ValueError("evaluator did not affirm report verification")
            _emit("verified", "Integrity checked against operator-selected anchors; no runtime acceptance")
            return 0
        if args.command == "report":
            evaluator = _evaluator()
            report = evaluator.build_report(
                _json(args.schedule), _mapping(args.records), pins=_pins(args.pins),
                config=_mapping(args.config), price=_mapping(args.price),
            )
            output = (evaluator.report_html(report) if args.format == "html" else
                      json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
            path = _private_output(args.private_dir, args.name, output)
            _emit("complete", "Private report constructed; no model/runtime acceptance", private_artifact=str(path))
            return 0
        raise ValueError("unknown command")
    except UnavailableError as exc:
        _emit("unavailable", str(exc))
        return 3
    except (OSError, ValueError, TypeError, AttributeError, ImportError, KeyError, IndexError) as exc:
        # Do not echo private evaluator/input exception contents to the console.
        _emit("error", f"{type(exc).__name__}: refused; inspect trusted inputs/integration privately")
        return 2


if __name__ == "__main__":
    sys.exit(main())
