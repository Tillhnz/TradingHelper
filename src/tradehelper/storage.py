"""SQLite-Speicher für Watchlist, Alarme und Alarm-Historie."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY,
    note TEXT DEFAULT '',
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    kind TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    interval TEXT NOT NULL DEFAULT '1d',
    once INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    last_triggered TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    message TEXT NOT NULL,
    triggered_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Alert:
    id: int
    symbol: str
    kind: str
    params: dict = field(default_factory=dict)
    interval: str = "1d"
    once: bool = False
    active: bool = True
    last_triggered: str | None = None
    created_at: str = ""

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Alert":
        return cls(
            id=row["id"],
            symbol=row["symbol"],
            kind=row["kind"],
            params=json.loads(row["params"] or "{}"),
            interval=row["interval"],
            once=bool(row["once"]),
            active=bool(row["active"]),
            last_triggered=row["last_triggered"],
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class Storage:
    def __init__(self, path: Path | str):
        self.path = str(path)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- Watchlist ---------------------------------------------------------
    def watchlist(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM watchlist ORDER BY symbol")]

    def watchlist_symbols(self) -> list[str]:
        return [w["symbol"] for w in self.watchlist()]

    def add_symbol(self, symbol: str, note: str = "") -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO watchlist(symbol, note, added_at) VALUES (?,?,?) "
                "ON CONFLICT(symbol) DO UPDATE SET note=excluded.note",
                (symbol.upper(), note, now_iso()),
            )

    def remove_symbol(self, symbol: str) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM watchlist WHERE symbol=?", (symbol.upper(),)).rowcount > 0

    # --- Alarme ------------------------------------------------------------
    def add_alert(self, symbol: str, kind: str, params: dict, interval: str = "1d", once: bool = False) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO alerts(symbol, kind, params, interval, once, created_at) VALUES (?,?,?,?,?,?)",
                (symbol.upper(), kind, json.dumps(params), interval, int(once), now_iso()),
            )
            return int(cur.lastrowid)

    def alerts(self, active_only: bool = False) -> list[Alert]:
        q = "SELECT * FROM alerts" + (" WHERE active=1" if active_only else "") + " ORDER BY id"
        with self._conn() as c:
            return [Alert.from_row(r) for r in c.execute(q)]

    def get_alert(self, alert_id: int) -> Alert | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM alerts WHERE id=?", (alert_id,)).fetchone()
            return Alert.from_row(row) if row else None

    def remove_alert(self, alert_id: int) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM alerts WHERE id=?", (alert_id,)).rowcount > 0

    def set_alert_active(self, alert_id: int, active: bool) -> bool:
        with self._conn() as c:
            return c.execute("UPDATE alerts SET active=? WHERE id=?", (int(active), alert_id)).rowcount > 0

    def mark_triggered(self, alert: Alert, message: str) -> None:
        ts = now_iso()
        with self._conn() as c:
            c.execute(
                "UPDATE alerts SET last_triggered=?, active=? WHERE id=?",
                (ts, 0 if alert.once else 1, alert.id),
            )
            c.execute(
                "INSERT INTO alert_log(alert_id, symbol, message, triggered_at) VALUES (?,?,?,?)",
                (alert.id, alert.symbol, message, ts),
            )

    def alert_log(self, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            return [
                dict(r)
                for r in c.execute("SELECT * FROM alert_log ORDER BY id DESC LIMIT ?", (limit,))
            ]
