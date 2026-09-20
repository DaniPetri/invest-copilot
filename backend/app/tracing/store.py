"""SQLite trace store (SPEC §8, §9): one row per request plus every SSE event in order.

Only the *redacted* user message is stored; PII never reaches this database.
"""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    trace_id    TEXT PRIMARY KEY,
    started_at  TEXT NOT NULL,
    mode        TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    message     TEXT NOT NULL,
    intent      TEXT,
    status      TEXT NOT NULL DEFAULT 'running',
    total_ms    INTEGER,
    cost_eur    REAL
);
CREATE TABLE IF NOT EXISTS events (
    trace_id TEXT NOT NULL REFERENCES traces(trace_id),
    seq      INTEGER NOT NULL,
    t_ms     INTEGER NOT NULL,
    event    TEXT NOT NULL,
    data     TEXT NOT NULL,
    PRIMARY KEY (trace_id, seq)
);
"""


class TraceStore:
    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def start(self, trace_id: str, started_at: str, mode: str, customer_id: str, message: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO traces (trace_id, started_at, mode, customer_id, message) VALUES (?, ?, ?, ?, ?)",
                (trace_id, started_at, mode, customer_id, message),
            )

    def add_event(self, trace_id: str, seq: int, t_ms: int, event: str, data: dict[str, Any]) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO events (trace_id, seq, t_ms, event, data) VALUES (?, ?, ?, ?, ?)",
                (trace_id, seq, t_ms, event, json.dumps(data, ensure_ascii=False)),
            )

    def set_intent(self, trace_id: str, intent: str) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE traces SET intent = ? WHERE trace_id = ?", (intent, trace_id))

    def finish(self, trace_id: str, status: str, total_ms: int, cost_eur: float) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE traces SET status = ?, total_ms = ?, cost_eur = ? WHERE trace_id = ?",
                (status, total_ms, cost_eur, trace_id),
            )

    def get(self, trace_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM traces WHERE trace_id = ?", (trace_id,)).fetchone()
            if row is None:
                return None
            events = self._db.execute(
                "SELECT seq, t_ms, event, data FROM events WHERE trace_id = ? ORDER BY seq", (trace_id,)
            ).fetchall()
        return {
            **dict(row),
            "events": [
                {"seq": e["seq"], "t_ms": e["t_ms"], "event": e["event"], "data": json.loads(e["data"])} for e in events
            ],
        }

    def close(self) -> None:
        with self._lock:
            self._db.close()
