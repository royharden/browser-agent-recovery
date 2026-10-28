"""Private original-development backend SOURCE; no import-time execution.

Canonical Linux/browser hooks are unavailable. Explicit convenience runs reuse
the authority and public scripted session; they do not qualify isolation, real
DOM installation, research freezing, independent truth or model performance.
"""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from uuid import uuid4

from .cli import AdmissionPort, FixtureRequest, PortResult


class DevelopmentOrchestrationPort(Protocol):
    """D3-owned schedule/runner seam; no default schedule or truth producer."""
    def matrix(self, request: FixtureRequest) -> PortResult: ...
    def freeze(self, request: FixtureRequest) -> PortResult: ...


def _private_root(path: Path | None) -> Path:
    if path is None or not path.is_absolute():
        raise ValueError("explicit absolute private DB root required")
    # Reject links/junctions at every existing component, including ancestors.
    # A private operator-controlled root/ACL is still required against races.
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("linked private roots are refused")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir() or any("onedrive" in part.casefold() for part in resolved.parts):
        raise ValueError("existing private root outside OneDrive required")
    product = Path(__file__).resolve().parents[2]
    if resolved == product or product in resolved.parents:
        raise ValueError("private root must be outside product source")
    return resolved


def _write(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")


class DevelopmentBackend:
    """Trusted operator object; never pass it or private outputs to an actor.

    Inputs are external anchors, never reconstructed from receipt identities.
    The admission producer remains injected until its accepted source joins.
    """
    def __init__(
        self, *, admission: AdmissionPort | None = None,
        document: Mapping[str, Any] | None = None,
        expected_hashes: Mapping[str, str] | None = None,
        builder_ids: Sequence[str] = (), trusted_ids: Sequence[str] = (),
        db_root: Path | None = None,
        orchestration: DevelopmentOrchestrationPort | None = None,
    ):
        self._admission = admission
        self._document = document
        self._expected_hashes = dict(expected_hashes or {})
        self._builder_ids, self._trusted_ids = tuple(builder_ids), tuple(trusted_ids)
        self._db_root, self._orchestration = db_root, orchestration

    def _gate(self) -> PortResult | None:
        if (self._admission is None or self._document is None
                or not self._expected_hashes or not self._builder_ids or not self._trusted_ids):
            return PortResult("pending", "Genuine external admission inputs/producer missing; nothing executed")
        decision = self._admission.admit(
            self._document, expected_hashes=self._expected_hashes,
            builder_ids=self._builder_ids, trusted_ids=self._trusted_ids,
        )
        if decision.state == "PASS":
            return None
        if decision.state == "FAIL":
            return PortResult("failed", "External admission FAIL; all execution modes skipped")
        if decision.state == "PENDING":
            return PortResult("pending", "External admission PENDING; nothing executed")
        raise ValueError("invalid admission state")

    @staticmethod
    def _validate(request: FixtureRequest) -> None:
        if (request.task not in {"F1", "F2", "F3"}
                or request.policy not in {"R0", "R1", "R2", "R3", "R23"}
                or request.profile not in {"canonical", "in_process_convenience"}
                or request.condition not in {"clean", "EXPIRED_VIEW", "STALE_ID", "INTERRUPTED_ACTION"}
                or request.mode != "fixture"):
            raise ValueError("closed development selection required")
        for value, low, high in ((request.seed, 0, 999), (request.max_actions, 1, 40),
                                 (request.max_probes, 1, 40),
                                 (request.horizon_ns, 1, 180_000_000_000)):
            if type(value) is not int or not low <= value <= high:
                raise ValueError("development caps outside closed bounds")
        if type(request.lag_ns) is not int or request.lag_ns not in {0, 2_000_000_000}:
            raise ValueError("operator history lag must be 0 or 2 seconds")

    def matrix(self, request: FixtureRequest) -> PortResult:
        blocked = self._gate()
        if blocked is not None:
            return blocked
        self._validate(request)
        if self._orchestration is None:
            return PortResult("unavailable", "D3 matrix runner seam unjoined; nothing scheduled or executed")
        return self._orchestration.matrix(request)

    def freeze(self, request: FixtureRequest) -> PortResult:
        blocked = self._gate()
        if blocked is not None:
            return blocked
        self._validate(request)
        if self._orchestration is None:
            return PortResult("unavailable", "D3 source-schedule seam unjoined; no research freeze or independent receipt")
        return self._orchestration.freeze(request)

    def run(self, request: FixtureRequest) -> PortResult:
        blocked = self._gate()
        if blocked is not None:
            return blocked
        self._validate(request)
        if request.profile == "canonical":
            return PortResult("unavailable", "Canonical Linux/browser hooks unavailable; nothing executed")
        root = _private_root(self._db_root)
        # All runtime modules are lazy and strictly downstream of real admission.
        from .authority import Authority
        from .driver import DevelopmentTask
        from .faults import FaultPlan
        from .lag import HistoryLag
        from .scripted import run_scripted
        from .trusted_bridge import create_development_session

        directory = root / ("development-" + uuid4().hex)
        directory.mkdir(mode=0o700, exist_ok=False)
        if directory.resolve(strict=True).parent != root:
            raise ValueError("private run containment failure")
        database = directory / "authority.sqlite3"
        # Reserve exclusively before SQLite opens; never reopen an existing run.
        with database.open("xb"):
            pass
        authority = None
        session = None
        task = None
        outcome = None
        stopped = False
        executed = False
        error = ""
        seal = None
        try:
            authority = Authority(database)
            task = DevelopmentTask(
                authority, request.task, request.seed,
                fault=None if request.condition == "clean" else FaultPlan(request.condition),
                lag=HistoryLag(request.lag_ns),
            )
            session = create_development_session(
                task, "http://127.0.0.1:20000", max_actions=request.max_actions,
                max_probes=request.max_probes, run_budget_ns=request.horizon_ns,
            )
            if not callable(getattr(session, "close", None)):
                raise ValueError("logical session stop hook unavailable")
            executed = True
            outcome = run_scripted(session, request.policy)
        except Exception as exc:
            error = type(exc).__name__
        finally:
            try:
                if session is not None:
                    session.close()
                    stopped = True
                else:
                    # No actor session was created; no worker was launched.
                    stopped = True
                if authority is not None and task is not None and stopped:
                    seal = authority.seal(task.public)
                    _write(directory / "seal.json", seal)
            except Exception as exc:
                error = error or type(exc).__name__
            finally:
                if authority is not None:
                    try:
                        authority.close()
                    except Exception as exc:
                        error = error or type(exc).__name__
        disposition = getattr(getattr(outcome, "action_result", None), "disposition", None)
        unknown = (bool(error) or not stopped or seal is None or outcome is None
                   or outcome.status != "authored" or disposition == "harness_unknown"
                   or getattr(outcome.finish_receipt, "status", None) != "acknowledged")
        record = {
            "schema": "rlab.development-record.v1", "selection": asdict(request),
            "execution": "unknown" if unknown else "returned",
            "attempted": executed, "error_type": error or None,
            "outcome": None if outcome is None else asdict(outcome),
            "logical_session_stopped": stopped, "os_worker": "not_launched",
            "profile": "in_process_convenience", "sandbox": "unqualified",
            "model_measurement": "not_yet_measured", "oracle": "unqualified",
            "scorer_truth": "not_supplied", "validation": "runtime_unverified",
            "current_call_cost": {"state": "known_zero", "amount": 0, "basis": "authored_offline"}
                if executed else {"state": "unknown", "amount": None},
            "media": {"trace": "not_requested", "video": "not_requested"},
            "private_seal": "seal.json" if seal is not None else None,
        }
        _write(directory / "record.json", record)
        return PortResult("failed" if unknown else "complete",
                          "Private authored development record; no oracle/model/isolation acceptance",
                          {"private_directory": str(directory), "execution": record["execution"]})
