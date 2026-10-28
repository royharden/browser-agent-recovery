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


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class Authority:
    def __init__(self, path: Path):
        if not path.is_absolute():
            raise ValueError("Use an absolute authority-owned DB path outside OneDrive")
        self._db = sqlite3.connect(path, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self.clock_id = uuid.uuid4().hex
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
        """)

    def close(self) -> None:
        self._db.close()

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

    def mutate(self, task: PublicTask, intent: Intent, request_id: str,
               origin: Origin) -> dict[str, object]:
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
            ns = time.monotonic_ns()
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
            self._db.execute("COMMIT")
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
        started = time.monotonic_ns()
        run = self._run(task.run_id, task.epoch)
        latest = run["version"]
        n = latest if visible_through is None else max(0, min(latest, visible_through))
        rows = self._db.execute("SELECT * FROM effects WHERE run=? AND version<=? ORDER BY seq",
                                (task.run_id, n)).fetchall()
        transitions = tuple(Transition(r["kind"], r["target"],
                            tuple(sorted(json.loads(r["payload"]).items())), r["version"])
                            for r in rows)
        return HistoryRead(task.run_id, task.epoch, self.clock_id, request_id,
                           started, time.monotonic_ns(), n, latest, transitions)

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
            self._db.execute("UPDATE runs SET sealed=1 WHERE run=?", (task.run_id,))
            bundle = {"schema": "rlab.evidence.v1", "run": run, "effects": effects,
                      "attempts": attempts, "state": items,
                      "terminal": {"sealed": True, "ns": time.monotonic_ns(),
                                   "clock_id": self.clock_id}}
            digest = hashlib.sha256(canonical(bundle).encode()).hexdigest()
            self._db.execute("COMMIT")
            return {"bundle": bundle, "sha256": digest}
        except Exception:
            self._db.execute("ROLLBACK")
            raise
