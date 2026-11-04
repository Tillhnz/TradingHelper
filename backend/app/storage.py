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
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    token_version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    quantity REAL NOT NULL,
    buy_price REAL NOT NULL,
    buy_date TEXT NOT NULL,
    fees REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT '',
    stop REAL,
    target REAL,
    note TEXT NOT NULL DEFAULT '',
    sell_price REAL,
    sell_date TEXT,
    sell_fees REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_positions (
    symbol TEXT PRIMARY KEY,
    shares REAL NOT NULL,
    entry REAL NOT NULL,
    entry_day TEXT NOT NULL,
    cost REAL NOT NULL,
    stop REAL,
    target REAL,
    checked_day TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    shares REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL NOT NULL,
    day TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    pl REAL,
    pl_pct REAL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_equity (
    day TEXT PRIMARY KEY,
    equity REAL NOT NULL,
    cash REAL NOT NULL
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
    currency: str = ""  # Währung der Alarmwerte; leer = Handelswährung
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
            currency=row["currency"] if "currency" in row.keys() else "",
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
            self._migrate(c)

    @staticmethod
    def _migrate(c: sqlite3.Connection) -> None:
        """Spalten nachrüsten, die ältere Versionen noch nicht hatten."""
        for table, col, ddl in [
            ("watchlist", "name", "TEXT"),
            ("watchlist", "exchange", "TEXT"),
            ("watchlist", "currency", "TEXT"),
            ("watchlist", "ticker", "TEXT"),
            ("alerts", "currency", "TEXT NOT NULL DEFAULT ''"),
        ]:
            cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

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

    def add_symbol(self, symbol: str, note: str = "", name: str | None = None, exchange: str | None = None,
                   currency: str | None = None, ticker: str | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO watchlist(symbol, note, added_at, name, exchange, currency, ticker) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(symbol) DO UPDATE SET note=excluded.note, name=COALESCE(excluded.name, name), "
                "exchange=COALESCE(excluded.exchange, exchange), currency=COALESCE(excluded.currency, currency), "
                "ticker=COALESCE(excluded.ticker, ticker)",
                (symbol.upper(), note, now_iso(), name, exchange, currency, ticker),
            )

    def update_meta(self, symbol: str, name: str | None, exchange: str | None, currency: str | None) -> None:
        with self._conn() as c:
            c.execute("UPDATE watchlist SET name=?, exchange=?, currency=? WHERE symbol=?",
                      (name, exchange, currency, symbol.upper()))

    def remove_symbol(self, symbol: str) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM watchlist WHERE symbol=?", (symbol.upper(),)).rowcount > 0

    # --- Alarme ------------------------------------------------------------
    def add_alert(self, symbol: str, kind: str, params: dict, interval: str = "1d", once: bool = False,
                  currency: str = "") -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO alerts(symbol, kind, params, interval, once, created_at, currency) VALUES (?,?,?,?,?,?,?)",
                (symbol.upper(), kind, json.dumps(params), interval, int(once), now_iso(), currency or ""),
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

    # --- Benutzer (ein Konto, angelegt beim ersten Aufruf) -------------------
    def user_count(self) -> int:
        with self._conn() as c:
            return int(c.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def create_user(self, username: str, password_hash: str) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO users(username, password_hash, created_at) VALUES (?,?,?)",
                (username, password_hash, now_iso()),
            )
            return int(cur.lastrowid)

    def get_user(self, user_id: int | None = None, username: str | None = None) -> dict | None:
        with self._conn() as c:
            if user_id is not None:
                row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            else:
                row = c.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
            return dict(row) if row else None

    def set_password(self, user_id: int, password_hash: str) -> None:
        """Neues Passwort; erhöht token_version, damit alte Anmeldungen ungültig werden."""
        with self._conn() as c:
            c.execute(
                "UPDATE users SET password_hash=?, token_version=token_version+1 WHERE id=?",
                (password_hash, user_id),
            )

    def delete_users(self) -> int:
        with self._conn() as c:
            return c.execute("DELETE FROM users").rowcount

    # --- Einstellungen aus der Oberfläche ------------------------------------
    def app_settings(self) -> dict[str, str]:
        with self._conn() as c:
            return {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM app_settings")}

    def set_app_setting(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO app_settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def update_note(self, symbol: str, note: str) -> bool:
        with self._conn() as c:
            return c.execute("UPDATE watchlist SET note=? WHERE symbol=?", (note, symbol.upper())).rowcount > 0

    # --- Positionen (erfasste Käufe) -----------------------------------------
    POSITION_FIELDS = ("symbol", "quantity", "buy_price", "buy_date", "fees", "currency", "stop", "target", "note",
                       "sell_price", "sell_date", "sell_fees")

    def positions(self, symbol: str | None = None, open_only: bool = False) -> list[dict]:
        q, args = "SELECT * FROM positions WHERE 1=1", []
        if symbol:
            q += " AND symbol=?"
            args.append(symbol.upper())
        if open_only:
            q += " AND sell_date IS NULL"
        with self._conn() as c:
            return [dict(r) for r in c.execute(q + " ORDER BY buy_date, id", args)]

    def get_position(self, pos_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM positions WHERE id=?", (pos_id,)).fetchone()
            return dict(row) if row else None

    def add_position(self, data: dict) -> int:
        cols = [k for k in self.POSITION_FIELDS if k in data]
        vals = [data[k].upper() if k == "symbol" else data[k] for k in cols]
        with self._conn() as c:
            cur = c.execute(
                f"INSERT INTO positions({', '.join(cols)}, created_at) VALUES ({', '.join('?' * len(cols))}, ?)",
                (*vals, now_iso()),
            )
            return int(cur.lastrowid)

    def update_position(self, pos_id: int, data: dict) -> bool:
        cols = [k for k in self.POSITION_FIELDS if k in data and k != "symbol"]
        if not cols:
            return self.get_position(pos_id) is not None
        with self._conn() as c:
            return c.execute(f"UPDATE positions SET {', '.join(f'{k}=?' for k in cols)} WHERE id=?",
                             (*[data[k] for k in cols], pos_id)).rowcount > 0

    def remove_position(self, pos_id: int) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM positions WHERE id=?", (pos_id,)).rowcount > 0

    def alert_log(self, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            return [
                dict(r)
                for r in c.execute("SELECT * FROM alert_log ORDER BY id DESC LIMIT ?", (limit,))
            ]

    # --- Schattendepot -------------------------------------------------------
    def paper_state(self) -> dict[str, str]:
        with self._conn() as c:
            return {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM paper_state")}

    def set_paper_state(self, **values) -> None:
        with self._conn() as c:
            for k, v in values.items():
                c.execute("INSERT INTO paper_state(key, value) VALUES (?,?) "
                          "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))

    def paper_positions(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM paper_positions ORDER BY entry_day, symbol")]

    def save_paper_position(self, pos: dict) -> None:
        cols = ("symbol", "shares", "entry", "entry_day", "cost", "stop", "target", "checked_day", "reason")
        with self._conn() as c:
            c.execute(f"INSERT OR REPLACE INTO paper_positions({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                      tuple(pos.get(k) for k in cols))

    def remove_paper_position(self, symbol: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM paper_positions WHERE symbol=?", (symbol,))

    def add_paper_trade(self, t: dict) -> None:
        cols = ("symbol", "side", "shares", "price", "fee", "day", "reason", "pl", "pl_pct")
        with self._conn() as c:
            c.execute(f"INSERT INTO paper_trades({', '.join(cols)}, created_at) VALUES ({', '.join('?' * len(cols))}, ?)",
                      (*[t.get(k) for k in cols], now_iso()))

    def paper_trades(self, limit: int = 500) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM paper_trades ORDER BY id DESC LIMIT ?", (limit,))]

    def set_paper_equity(self, day: str, equity: float, cash: float) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO paper_equity(day, equity, cash) VALUES (?,?,?)", (day, equity, cash))

    def paper_equity(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM paper_equity ORDER BY day")]

    def reset_paper(self) -> None:
        with self._conn() as c:
            for t in ("paper_positions", "paper_trades", "paper_equity"):
                c.execute(f"DELETE FROM {t}")
            c.execute("DELETE FROM paper_state WHERE key != 'backtest'")
