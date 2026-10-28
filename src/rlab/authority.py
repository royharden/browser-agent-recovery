"""Authority-only SQLite source. Never hand this object to an actor/worker.

No deduplication: repeated orders/tickets are real additional effects. State,
effect and attempt rows are committed together. HTTP/process isolation is a
later integration; this module makes no sandbox or durability qualification claim.
"""
import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path

from .contracts import HistoryRead, Intent, Origin, PublicTask, Transition
from .faults import FaultPlan
from .lag import HistoryLag


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class Authority:
    def __init__(self, path: Path):
        if not path.is_absolute():
            raise ValueError("Use an absolute authority-owned DB path outside OneDrive")
        self._db = sqlite3.connect(path, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self.clock_id = uuid.uuid4().hex
        # This serialized authority owns the process clock. Reopened runs are
        # refused by _run, so timing anchors never cross a process restart.
        self._committed_ns: dict[tuple[str, int], int] = {}
        self._db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
          run TEXT PRIMARY KEY, epoch TEXT NOT NULL, clock TEXT NOT NULL,
          family TEXT NOT NULL, version INTEGER NOT NULL, sealed INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS items (
          run TEXT NOT NULL, id TEXT NOT NULL, deleted INTEGER NOT NULL,
          PRIMARY KEY(run,id));
        CREATE TABLE IF NOT EXISTS attempts (
          run TEXT NOT NULL, seq INTEGER NOT NULL, request TEXT NOT NULL,
          root TEXT NOT NULL, origin TEXT NOT NULL, operation TEXT NOT NULL,
          target TEXT NOT NULL, payload TEXT NOT NULL, ns INTEGER NOT NULL,
          PRIMARY KEY(run,seq));
        CREATE TABLE IF NOT EXISTS effects (
          run TEXT NOT NULL, epoch TEXT NOT NULL, seq INTEGER NOT NULL,
          ns INTEGER NOT NULL, clock TEXT NOT NULL, kind TEXT NOT NULL,
          target TEXT NOT NULL, payload TEXT NOT NULL, request TEXT NOT NULL,
          version INTEGER NOT NULL, PRIMARY KEY(run,seq));
        CREATE TABLE IF NOT EXISTS visibility (
          run TEXT PRIMARY KEY, delay_ns INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS faults (
          run TEXT PRIMARY KEY, epoch TEXT NOT NULL, clock TEXT NOT NULL,
          kind TEXT NOT NULL, boundary INTEGER NOT NULL, seen INTEGER NOT NULL,
          selected_request TEXT, status TEXT NOT NULL, onset_ns INTEGER,
          snapshot TEXT);
        """)

    def close(self) -> None:
        self._db.close()

    def now_ns(self) -> int:
        """Trusted same-domain timestamp, never a worker supplied clock."""
        return time.monotonic_ns()

    def _run(self, run_id: str, epoch: str) -> sqlite3.Row:
        row = self._db.execute("SELECT * FROM runs WHERE run=?", (run_id,)).fetchone()
        if row is None or row["epoch"] != epoch or row["sealed"]:
            raise ValueError("unknown, cross-epoch or sealed run")
        if row["clock"] != self.clock_id:
            raise ValueError("CLOCK_DOMAIN: authority restart requires a fresh run")
        return row

    def setup(self, family: str, seed: int) -> PublicTask:
        if family not in {"F1", "F2", "F3"} or not 0 <= seed <= 999:
            raise ValueError("development families/seeds only")
        run, epoch = uuid.uuid4().hex, uuid.uuid4().hex
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._db.execute("INSERT INTO runs VALUES (?,?,?,?,0,0)",
                             (run, epoch, self.clock_id, family))
            self._db.execute("INSERT INTO visibility VALUES (?,0)", (run,))
            # Original synthetic names only; no external data or expected answers.
            for name in (f"widget-{seed}", f"widget-{seed}-extra"):
                self._db.execute("INSERT INTO items VALUES (?,?,0)", (run, name))
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        goals = {"F1": f"Order widget-{seed}, quantity 1.",
                 "F2": f"Create one support ticket in general with body widget-{seed}.",
                 "F3": f"Delete exactly widget-{seed}."}
        return PublicTask(run, epoch, goals[family], f"/tasks/{run}")

    def configure_lag(self, task: PublicTask, lag: HistoryLag) -> None:
        """Operator setup only, before effects or submission boundaries."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            run = self._run(task.run_id, task.epoch)
            attempts = self._db.execute("SELECT COUNT(*) FROM attempts WHERE run=?",
                                        (task.run_id,)).fetchone()[0]
            fault = self._db.execute("SELECT seen FROM faults WHERE run=?",
                                     (task.run_id,)).fetchone()
            if run["version"] or attempts or (fault and fault["seen"]):
                raise ValueError("lag must be configured before actions")
            self._db.execute("UPDATE visibility SET delay_ns=? WHERE run=?",
                             (lag.delay_ns, task.run_id))
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def configure_fault(self, task: PublicTask, plan: FaultPlan) -> None:
        """One immutable plan per run; never callable from the public port."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            run = self._run(task.run_id, task.epoch)
            attempts = self._db.execute("SELECT COUNT(*) FROM attempts WHERE run=?",
                                        (task.run_id,)).fetchone()[0]
            if run["version"] or attempts:
                raise ValueError("fault must be configured before actions")
            self._db.execute("INSERT INTO faults VALUES (?,?,?,?,?,0,NULL,'armed',NULL,NULL)",
                             (task.run_id, task.epoch, self.clock_id,
                              plan.kind, plan.boundary))
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def prepare_boundary(self, task: PublicTask, request_id: str) -> str | None:
        """Operator semantic-submission hook; claim exactly one selected boundary.

        The driver calls once per actual submission, not per snapshot or poll.
        A selected boundary never becomes armed again after an adapter failure.
        """
        if not request_id:
            raise ValueError("executor request identity required")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._run(task.run_id, task.epoch)
            fault = self._db.execute("SELECT * FROM faults WHERE run=?",
                                     (task.run_id,)).fetchone()
            kind = None
            if fault and fault["status"] == "selected":
                raise RuntimeError("unfinished selected fault boundary; seal as harness error")
            if fault and fault["status"] == "armed":
                seen = fault["seen"] + 1
                selected = seen == fault["boundary"]
                self._db.execute(
                    "UPDATE faults SET seen=?,selected_request=?,status=? WHERE run=?",
                    (seen, request_id if selected else None,
                     "selected" if selected else "armed", task.run_id))
                if selected:
                    kind = fault["kind"]
            self._db.execute("COMMIT")
            return kind
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def cancel_boundary(self, task: PublicTask, request_id: str) -> None:
        """Trusted guard refusal: an unissued interrupted action did not fire."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._run(task.run_id, task.epoch)
            self._db.execute(
                "UPDATE faults SET status='not_fired' WHERE run=? AND selected_request=? "
                "AND status='selected' AND kind='INTERRUPTED_ACTION'",
                (task.run_id, request_id))
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def _fire_fault(self, task: PublicTask, request_id: str,
                    kind: str, snapshot_epoch: str) -> None:
        fault = self._db.execute("SELECT * FROM faults WHERE run=?",
                                 (task.run_id,)).fetchone()
        if (fault is None or fault["epoch"] != task.epoch
                or fault["clock"] != self.clock_id or fault["kind"] != kind
                or fault["selected_request"] != request_id
                or fault["status"] != "selected"):
            raise ValueError("fault boundary identity/state mismatch")
        self._db.execute("UPDATE faults SET status='fired',onset_ns=?,snapshot=? WHERE run=?",
                         (self.now_ns(), snapshot_epoch, task.run_id))

    def fire_boundary(self, task: PublicTask, request_id: str,
                      kind: str, snapshot_epoch: str) -> None:
        """After trusted expiry or acknowledged remap; before any mutation."""
        if kind not in {"EXPIRED_VIEW", "STALE_ID"}:
            raise ValueError("post-commit faults must fire in mutate transaction")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._run(task.run_id, task.epoch)
            self._fire_fault(task, request_id, kind, snapshot_epoch)
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def mutate(self, task: PublicTask, intent: Intent, request_id: str,
               origin: Origin, *, interrupted: bool = False,
               snapshot_epoch: str = "") -> dict[str, object]:
        if origin not in {"agent_direct", "controller_retry", "controller_resolve"}:
            raise ValueError("invalid immediate origin")
        if not request_id or not intent.root_intent_id:
            raise ValueError("executor lineage required")
        if len(dict(intent.payload)) != len(intent.payload):
            raise ValueError("duplicate payload fields")
        payload = dict(intent.payload)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            run = self._run(task.run_id, task.epoch)
            expected = {"F1": "order", "F2": "ticket", "F3": "delete"}[run["family"]]
            if intent.operation != expected:
                raise ValueError("operation outside family")
            item = self._db.execute("SELECT deleted FROM items WHERE run=? AND id=?",
                                    (task.run_id, intent.target_id)).fetchone()
            if intent.operation in {"order", "delete"} and item is None:
                raise ValueError("unknown visible item")
            if intent.operation == "order" and payload != {"quantity": "1"}:
                raise ValueError("development order requires quantity 1")
            if intent.operation == "ticket" and (
                    intent.target_id not in {"general", "billing"}
                    or set(payload) != {"body"} or not payload["body"]):
                raise ValueError("invalid ticket")
            if intent.operation == "delete" and payload:
                raise ValueError("delete has no form fields")
            ns = self.now_ns()
            attempt = self._db.execute(
                "SELECT COUNT(*) FROM attempts WHERE run=?", (task.run_id,)).fetchone()[0] + 1
            self._db.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?)",
                             (task.run_id, attempt, request_id, intent.root_intent_id,
                              origin, intent.operation, intent.target_id,
                              canonical(payload), ns))
            changed = not (intent.operation == "delete" and item["deleted"])
            version = run["version"] + int(changed)
            if changed:
                if intent.operation == "delete":
                    self._db.execute("UPDATE items SET deleted=1 WHERE run=? AND id=?",
                                     (task.run_id, intent.target_id))
                self._db.execute("INSERT INTO effects VALUES (?,?,?,?,?,?,?,?,?,?)",
                                 (task.run_id, task.epoch, version, ns, self.clock_id,
                                  intent.operation, intent.target_id, canonical(payload),
                                  request_id, version))
                self._db.execute("UPDATE runs SET version=? WHERE run=?", (version, task.run_id))
            if interrupted:
                # The fault marker and any actual effect commit atomically. A
                # repeated delete remains an attempt with changed=False.
                self._fire_fault(task, request_id, "INTERRUPTED_ACTION", snapshot_epoch)
            self._db.execute("COMMIT")
            if changed:
                self._committed_ns[task.run_id, version] = self.now_ns()
            return {"changed": changed, "state_version": version, "request_id": request_id}
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def history(self, task: PublicTask, request_id: str,
                visible_through: int | None = None) -> HistoryRead:
        """Ordinary public transitions, no private effect lineage/answers.

        The trusted driver stamps request start separately in production. This
        in-process seam uses the same authority clock solely for future dev wiring.
        visible_through is authority-only lag configuration, never actor input.
        """
        if not request_id:
            raise ValueError("fresh history request identity required")
        self._db.execute("BEGIN")
        try:
            started = self.now_ns()
            run = self._run(task.run_id, task.epoch)
            latest = run["version"]
            visibility = self._db.execute("SELECT delay_ns FROM visibility WHERE run=?",
                                          (task.run_id,)).fetchone()
            lag = HistoryLag(visibility[0] if visibility else 0)
            # Prefix by commit visibility, not by surviving objects. All rows
            # and both watermarks come from this one SQLite read snapshot.
            rows = self._db.execute("SELECT * FROM effects WHERE run=? ORDER BY seq",
                                    (task.run_id,)).fetchall()
            visible = []
            for row in rows:
                committed_ns = self._committed_ns.get((task.run_id, row["version"]))
                # Missing anchors withhold the prefix instead of publishing
                # unqualified timing. A post-commit anchor cannot predate the
                # actual commit, even if SQLite commit itself was slow.
                if committed_ns is None or committed_ns > lag.cutoff_ns(started):
                    break
                visible.append(row)
            n = len(visible)
            if visible_through is not None:
                n = min(n, max(0, visible_through))
            transitions = tuple(Transition(r["kind"], r["target"],
                                tuple(sorted(json.loads(r["payload"]).items())), r["version"])
                                for r in visible[:n])
            completed = self.now_ns()
            self._db.execute("COMMIT")
            return HistoryRead(task.run_id, task.epoch, self.clock_id, request_id,
                               started, completed, n, latest, transitions)
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def visible_items(self, task: PublicTask) -> tuple[str, ...]:
        """Public task page projection, not an actor DB interface."""
        self._run(task.run_id, task.epoch)
        return tuple(r[0] for r in self._db.execute(
            "SELECT id FROM items WHERE run=? AND deleted=0 ORDER BY id", (task.run_id,)))

    def seal(self, task: PublicTask) -> dict[str, object]:
        """Operator-only export; no scorer, acceptance claim or HTTP admin route."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            run = dict(self._run(task.run_id, task.epoch))
            effects = [dict(r) for r in self._db.execute(
                "SELECT * FROM effects WHERE run=? ORDER BY seq", (task.run_id,))]
            attempts = [dict(r) for r in self._db.execute(
                "SELECT * FROM attempts WHERE run=? ORDER BY seq", (task.run_id,))]
            items = [dict(r) for r in self._db.execute(
                "SELECT id,deleted FROM items WHERE run=? ORDER BY id", (task.run_id,))]
            fault = self._db.execute("SELECT * FROM faults WHERE run=?", (task.run_id,)).fetchone()
            control = dict(fault) if fault else {"kind": "clean", "status": "clean"}
            control["disposition"] = ("fired" if control["status"] == "fired"
                                      else "not_fired")
            control["harness_error"] = control["status"] == "selected"
            visibility = [{"version": effect["version"],
                           "committed_ns": self._committed_ns.get(
                               (task.run_id, effect["version"])),
                           "clock_id": self.clock_id} for effect in effects]
            self._db.execute("UPDATE runs SET sealed=1 WHERE run=?", (task.run_id,))
            bundle = {"schema": "rlab.evidence.v1", "run": run, "effects": effects,
                      "attempts": attempts, "state": items, "fault": control,
                      "visibility": visibility,
                      "terminal": {"sealed": True, "ns": self.now_ns(),
                                   "clock_id": self.clock_id}}
            digest = hashlib.sha256(canonical(bundle).encode()).hexdigest()
            self._db.execute("COMMIT")
            return {"bundle": bundle, "sha256": digest}
        except Exception:
            self._db.execute("ROLLBACK")
            raise
