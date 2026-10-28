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
    profile: Literal["canonical", "in_process_convenience"] = "canonical"
    condition: Literal["clean", "EXPIRED_VIEW", "STALE_ID", "INTERRUPTED_ACTION"] = "clean"
    lag_ns: int = 0


@dataclass(frozen=True)
class PortResult:
    status: Literal["complete", "pending", "unavailable", "failed"]
    detail: str
    artifact: Mapping[str, Any] | None = None


class FixturePort(Protocol):
    """Trusted host owns public action/snapshot orchestration and admission gate.

    Future producers must require a real admission PASS before execution, and
    skip every mode on FAIL. Joined admission/provider loop is unresolved.
    """
    def run(self, request: FixtureRequest) -> PortResult: ...
    def matrix(self, request: FixtureRequest) -> PortResult: ...
    def freeze(self, request: FixtureRequest) -> PortResult: ...


class AdmissionDecision(Protocol):
    @property
    def state(self) -> Literal["PASS", "PENDING", "FAIL"]: ...
    @property
    def reasons(self) -> tuple[str, ...]: ...
    def to_dict(self) -> Mapping[str, Any]: ...


class AdmissionPort(Protocol):
    def admit(
        self, document: Mapping[str, Any], *, expected_hashes: Mapping[str, str],
        builder_ids: Sequence[str], trusted_ids: Sequence[str] = (),
    ) -> AdmissionDecision: ...


class ProviderPort(Protocol):
    """Future seam only; live CLI execution remains closed."""
    def readiness(self) -> PortResult: ...


@dataclass(frozen=True)
class OperatorPorts:
    fixture: FixturePort | None = None
    admission: AdmissionPort | None = None
    provider: ProviderPort | None = None
    # Trusted embedding only. A JSON PASS/manifest cannot populate this object.
    source_schedule_admission: Any = None


class UnavailableError(Exception):
    pass


class AcceptedAdmissionPort:
    """Fixed accepted producer; trust anchors always remain caller supplied."""
    def admit(self, document: Mapping[str, Any], *, expected_hashes: Mapping[str, str],
              builder_ids: Sequence[str], trusted_ids: Sequence[str] = ()) -> AdmissionDecision:
        try:
            from .admission import admit
        except ImportError as exc:
            raise UnavailableError("accepted admission producer unavailable") from exc
        return admit(document, expected_hashes=expected_hashes,
                     builder_ids=builder_ids, trusted_ids=trusted_ids)


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


def _identifier(value: Any) -> bool:
    return (isinstance(value, str) and 1 <= len(value) <= 128
            and value == value.strip() and all(32 <= ord(char) <= 126 for char in value))


def _identities(path: Path) -> tuple[str, ...]:
    value = _json(path)
    if (not isinstance(value, list) or len(value) > 128
            or not all(_identifier(item) for item in value)
            or len(set(value)) != len(value)):
        raise ValueError("identities require at most 128 unique bounded ASCII strings")
    return tuple(value)


def _expected_hashes(path: Path) -> dict[str, str]:
    value = _mapping(path)
    if (not 1 <= len(value) <= 64 or any(
        re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", key) is None
        or not isinstance(digest, str) or SHA256.fullmatch(digest) is None
        for key, digest in value.items()
    )):
        raise ValueError("expected hashes require 1..64 bounded names and lowercase SHA256 values")
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
        command.add_argument("--profile", choices=("canonical", "in_process_convenience"), default="canonical")
        command.add_argument("--condition", choices=("clean", "EXPIRED_VIEW", "STALE_ID", "INTERRUPTED_ACTION"), default="clean")
        command.add_argument("--lag-ns", type=int, choices=(0, 2_000_000_000), default=0)
        command.add_argument("--db-root", type=Path)
        command.add_argument("--manifest", type=Path)
        command.add_argument("--expected-hashes", type=Path)
        command.add_argument("--builder-ids", type=Path)
        command.add_argument("--trusted-ids", type=Path)
        if name == "freeze":
            command.add_argument("--private-dir", required=True, type=Path)
            command.add_argument("--name", default="schedule.json")
            command.add_argument("--source-inputs", type=Path)
            command.add_argument("--source-expected-hashes", type=Path)
            command.add_argument("--source-expected-input-sha256", type=Path)
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
    admit.add_argument("--expected-hashes", type=Path)
    admit.add_argument("--builder-ids", type=Path)
    admit.add_argument("--trusted-ids", type=Path)
    return parser


def main(argv: Sequence[str] | None = None, *, ports: OperatorPorts | None = None) -> int:
    """Trusted embedding may inject ports; command-line artifacts cannot load code."""
    args = _parser().parse_args(argv)
    ports = ports or OperatorPorts(admission=AcceptedAdmissionPort())
    try:
        if args.command == "tasks":
            _emit("available", "Original development families only", tasks=[
                {"id": identifier, "operation": operation} for identifier, operation in TASKS
            ])
            return 0
        if args.command in ("run", "matrix", "freeze"):
            # Gate all modes before backend construction, DB creation or live refusal.
            if (ports.admission is None or any(value is None for value in (
                    args.manifest, args.expected_hashes, args.builder_ids, args.trusted_ids))):
                _emit("pending", "External admission producer and independent operator anchors required", state="PENDING")
                return 3
            manifest = args.manifest.resolve(strict=True)
            if any(manifest.samefile(path.resolve(strict=True)) for path in (
                    args.expected_hashes, args.builder_ids, args.trusted_ids)):
                raise ValueError("manifest must be distinct from operator anchors")
            document = _mapping(manifest)
            expected = _expected_hashes(args.expected_hashes)
            builders, trusted = _identities(args.builder_ids), _identities(args.trusted_ids)
            if not builders or not trusted:
                _emit("pending", "Independent builder and trusted identities required", state="PENDING")
                return 3
            decision = ports.admission.admit(document, expected_hashes=expected,
                                             builder_ids=builders, trusted_ids=trusted)
            if decision.state not in ("PASS", "PENDING", "FAIL"):
                raise ValueError("invalid admission state")
            if decision.state != "PASS":
                _emit("failed" if decision.state == "FAIL" else "pending",
                      "Admission blocks every execution mode", state=decision.state)
                return 2 if decision.state == "FAIL" else 3
            if args.mode == "live":
                raise UnavailableError("live execution unavailable: provider/admission/worker integration pending")
            if (args.max_actions > 40 or args.max_probes > 40
                    or not 0 <= args.seed <= 999):
                raise ValueError("development action/probe caps or seed outside closed bounds")
            request = FixtureRequest(
                args.task, args.policy, args.max_actions, args.max_probes, args.horizon_ns, args.seed,
                profile=args.profile, condition=args.condition, lag_ns=args.lag_ns,
            )
            fixture = ports.fixture
            if fixture is None:
                from .dev_backend import DevelopmentBackend, JoinedDevelopmentOrchestration
                orchestration = None
                if args.command == "freeze":
                    if any(value is None for value in (args.source_inputs, args.source_expected_hashes,
                                                       args.source_expected_input_sha256)):
                        _emit("pending", "Source schedule requires external full inputs and independent anchors")
                        return 3
                    inputs_path = args.source_inputs.resolve(strict=True)
                    if any(inputs_path.samefile(path.resolve(strict=True)) for path in (
                            args.source_expected_hashes, args.source_expected_input_sha256)):
                        raise ValueError("source inputs must differ from independent anchors")
                    orchestration = JoinedDevelopmentOrchestration(
                        inputs=_mapping(inputs_path), admission=ports.source_schedule_admission, port=None,
                        expected_input_sha256=_digest(args.source_expected_input_sha256),
                        expected_source_hashes=_expected_hashes(args.source_expected_hashes))
                fixture = DevelopmentBackend(
                    admission=ports.admission, document=document, expected_hashes=expected,
                    builder_ids=builders, trusted_ids=trusted, db_root=args.db_root,
                    orchestration=orchestration,
                )
            if args.command == "run":
                result = fixture.run(request)
            elif args.command == "matrix":
                result = fixture.matrix(request)
            else:
                result = fixture.freeze(request)
            if result.status != "complete":
                execution = (result.artifact or {}).get("execution", "not_run")
                if execution not in {"not_run", "unknown", "returned"}:
                    execution = "unknown"
                _emit(result.status, result.detail, execution=execution)
                return 2 if result.status == "failed" else 3
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
            if args.expected_hashes is None or args.builder_ids is None:
                _emit("pending", "Admission requires independently selected expected hashes and builder IDs",
                      state="PENDING")
                return 3
            manifest_path = args.manifest.resolve(strict=True)
            anchor_paths = [args.expected_hashes, args.builder_ids]
            if args.trusted_ids is not None:
                anchor_paths.append(args.trusted_ids)
            if any(manifest_path.samefile(path.resolve(strict=True)) for path in anchor_paths):
                raise ValueError("manifest must be distinct from operator anchor files")
            expected_hashes = _expected_hashes(args.expected_hashes)
            builder_ids = _identities(args.builder_ids)
            trusted_ids = () if args.trusted_ids is None else _identities(args.trusted_ids)
            if not builder_ids or not trusted_ids:
                _emit("pending", "Externally verified builder/trusted identities are required",
                      state="PENDING")
                return 3
            if ports.admission is None:
                _emit("unavailable", "Trusted custodian admission backend unavailable", state="PENDING")
                return 3
            decision = ports.admission.admit(
                _mapping(manifest_path), expected_hashes=expected_hashes,
                builder_ids=builder_ids, trusted_ids=trusted_ids,
            )
            if (decision.state not in ("PASS", "PENDING", "FAIL")
                    or not isinstance(decision.reasons, tuple) or len(decision.reasons) > 64
                    or any(not isinstance(reason, str) or len(reason) > 1024
                           for reason in decision.reasons)):
                raise ValueError("admission returned an invalid decision")
            # Private reasons/receipt IDs remain inside the trusted operator boundary.
            _emit(decision.state.lower(), "Admission decision; no runtime acceptance",
                  state=decision.state)
            return {"PASS": 0, "PENDING": 3, "FAIL": 2}[decision.state]
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
