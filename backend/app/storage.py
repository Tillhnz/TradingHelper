"""SQLite-Speicher. Alles, was einem Nutzer gehört (Watchlist, Alarme, Käufe, Schattendepot, eigene Einstellungen,
Chart-Zeichnungen), trägt eine user_id. Eine Storage-Instanz ist immer an einen Nutzer gebunden (Standard: 1 = Besitzer);
for_user() liefert dieselbe Datenbank für einen anderen Nutzer."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    user_id INTEGER NOT NULL DEFAULT 1,
    symbol TEXT NOT NULL,
    note TEXT DEFAULT '',
    added_at TEXT NOT NULL,
    name TEXT, exchange TEXT, currency TEXT, ticker TEXT,
    PRIMARY KEY (user_id, symbol)
);
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    symbol TEXT NOT NULL,
    kind TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    interval TEXT NOT NULL DEFAULT '1d',
    once INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    last_triggered TEXT,
    created_at TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    token_version INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS invites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token_hash TEXT NOT NULL UNIQUE,
    note TEXT NOT NULL DEFAULT '',
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_by INTEGER,
    used_at TEXT
);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);
CREATE TABLE IF NOT EXISTS chart_layouts (
    user_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, symbol)
);
CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    job TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
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
    created_at TEXT NOT NULL,
    trail_pct REAL,
    watch_state TEXT NOT NULL DEFAULT '',
    buy_time TEXT,
    sell_time TEXT
);
CREATE TABLE IF NOT EXISTS paper_state (
    user_id INTEGER NOT NULL DEFAULT 1,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);
CREATE TABLE IF NOT EXISTS paper_positions (
    user_id INTEGER NOT NULL DEFAULT 1,
    symbol TEXT NOT NULL,
    shares REAL NOT NULL,
    entry REAL NOT NULL,
    entry_day TEXT NOT NULL,
    cost REAL NOT NULL,
    stop REAL,
    target REAL,
    checked_day TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, symbol)
);
CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
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
CREATE TABLE IF NOT EXISTS paper_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    kind TEXT NOT NULL,
    limit_price REAL,
    stop REAL,
    target REAL,
    ref_price REAL,
    reason TEXT NOT NULL DEFAULT '',
    day TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    done_at TEXT
);
CREATE TABLE IF NOT EXISTS paper_equity (
    user_id INTEGER NOT NULL DEFAULT 1,
    day TEXT NOT NULL,
    equity REAL NOT NULL,
    cash REAL NOT NULL,
    PRIMARY KEY (user_id, day)
);
CREATE TABLE IF NOT EXISTS alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL DEFAULT 1,
    alert_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    message TEXT NOT NULL,
    triggered_at TEXT NOT NULL
);
"""

# Tabellen, deren Primärschlüssel früher ohne user_id war: werden einmalig umgebaut
_REBUILD = {
    "watchlist": ("symbol, note, added_at, name, exchange, currency, ticker", ["name", "exchange", "currency", "ticker"]),
    "paper_state": ("key, value", []),
    "paper_positions": ("symbol, shares, entry, entry_day, cost, stop, target, checked_day, reason", []),
    "paper_equity": ("day, equity, cash", []),
}
_ADD_USER = ("alerts", "positions", "paper_trades", "alert_log")


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
    def __init__(self, path: Path | str, user_id: int = 1):
        self.path = str(path)
        self.uid = int(user_id)
        with self._conn() as c:
            c.executescript(SCHEMA)  # fehlende Tabellen anlegen; vorhandene alte bleiben und werden migriert
            self._migrate(c)

    def for_user(self, user_id: int) -> "Storage":
        """Dieselbe Datenbank, gebunden an einen anderen Nutzer (ohne erneute Migration)."""
        other = object.__new__(Storage)
        other.path, other.uid = self.path, int(user_id)
        return other

    @staticmethod
    def _cols(c: sqlite3.Connection, table: str) -> set[str]:
        return {r[1] for r in c.execute(f"PRAGMA table_info({table})")}

    @classmethod
    def _migrate(cls, c: sqlite3.Connection) -> None:
        """Ältere Datenbanken nachrüsten. Bestehende Daten gehören danach Nutzer 1 (dem Besitzer)."""
        for table, col, ddl in [
            ("watchlist", "name", "TEXT"),
            ("watchlist", "exchange", "TEXT"),
            ("watchlist", "currency", "TEXT"),
            ("watchlist", "ticker", "TEXT"),
            ("alerts", "currency", "TEXT NOT NULL DEFAULT ''"),
            ("positions", "trail_pct", "REAL"),
            ("positions", "watch_state", "TEXT NOT NULL DEFAULT ''"),
            ("positions", "buy_time", "TEXT"),
            ("positions", "sell_time", "TEXT"),
            ("users", "is_admin", "INTEGER NOT NULL DEFAULT 0"),
        ]:
            if col not in cls._cols(c, table):
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
        for table in _ADD_USER:
            if "user_id" not in cls._cols(c, table):
                c.execute(f"ALTER TABLE {table} ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1")
        for table, (cols, _) in _REBUILD.items():
            if "user_id" in cls._cols(c, table):
                continue
            c.execute(f"ALTER TABLE {table} RENAME TO {table}_alt")
            c.executescript(SCHEMA)  # legt die Tabelle in neuer Form an
            c.execute(f"INSERT INTO {table}(user_id, {cols}) SELECT 1, {cols} FROM {table}_alt")
            c.execute(f"DROP TABLE {table}_alt")
        for table in ("alerts", "positions", "paper_trades", "alert_log"):
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user ON {table}(user_id)")
        # Der erste Nutzer ist der Besitzer und Admin
        if not c.execute("SELECT 1 FROM users WHERE is_admin=1").fetchone():
            c.execute("UPDATE users SET is_admin=1 WHERE id=(SELECT MIN(id) FROM users)")

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
            return [dict(r) for r in c.execute("SELECT * FROM watchlist WHERE user_id=? ORDER BY symbol", (self.uid,))]

    def watchlist_symbols(self) -> list[str]:
        return [w["symbol"] for w in self.watchlist()]

    def add_symbol(self, symbol: str, note: str = "", name: str | None = None, exchange: str | None = None,
                   currency: str | None = None, ticker: str | None = None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO watchlist(user_id, symbol, note, added_at, name, exchange, currency, ticker) "
                "VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(user_id, symbol) DO UPDATE SET note=excluded.note, name=COALESCE(excluded.name, name), "
                "exchange=COALESCE(excluded.exchange, exchange), currency=COALESCE(excluded.currency, currency), "
                "ticker=COALESCE(excluded.ticker, ticker)",
                (self.uid, symbol.upper(), note, now_iso(), name, exchange, currency, ticker),
            )

    def update_meta(self, symbol: str, name: str | None, exchange: str | None, currency: str | None) -> None:
        with self._conn() as c:
            c.execute("UPDATE watchlist SET name=?, exchange=?, currency=? WHERE user_id=? AND symbol=?",
                      (name, exchange, currency, self.uid, symbol.upper()))

    def remove_symbol(self, symbol: str) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM watchlist WHERE user_id=? AND symbol=?", (self.uid, symbol.upper())).rowcount > 0

    def update_note(self, symbol: str, note: str) -> bool:
        with self._conn() as c:
            return c.execute("UPDATE watchlist SET note=? WHERE user_id=? AND symbol=?",
                             (note, self.uid, symbol.upper())).rowcount > 0

    # --- Alarme ------------------------------------------------------------
    def add_alert(self, symbol: str, kind: str, params: dict, interval: str = "1d", once: bool = False,
                  currency: str = "") -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO alerts(user_id, symbol, kind, params, interval, once, created_at, currency) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (self.uid, symbol.upper(), kind, json.dumps(params), interval, int(once), now_iso(), currency or ""),
            )
            return int(cur.lastrowid)

    def alerts(self, active_only: bool = False) -> list[Alert]:
        q = "SELECT * FROM alerts WHERE user_id=?" + (" AND active=1" if active_only else "") + " ORDER BY id"
        with self._conn() as c:
            return [Alert.from_row(r) for r in c.execute(q, (self.uid,))]

    def get_alert(self, alert_id: int) -> Alert | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM alerts WHERE id=? AND user_id=?", (alert_id, self.uid)).fetchone()
            return Alert.from_row(row) if row else None

    def remove_alert(self, alert_id: int) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM alerts WHERE id=? AND user_id=?", (alert_id, self.uid)).rowcount > 0

    def set_alert_params(self, alert_id: int, params: dict) -> bool:
        with self._conn() as c:
            return c.execute("UPDATE alerts SET params=? WHERE id=? AND user_id=?",
                             (json.dumps(params), alert_id, self.uid)).rowcount > 0

    def set_alert_active(self, alert_id: int, active: bool) -> bool:
        with self._conn() as c:
            return c.execute("UPDATE alerts SET active=? WHERE id=? AND user_id=?",
                             (int(active), alert_id, self.uid)).rowcount > 0

    def mark_triggered(self, alert: Alert, message: str) -> None:
        ts = now_iso()
        with self._conn() as c:
            c.execute("UPDATE alerts SET last_triggered=?, active=? WHERE id=? AND user_id=?",
                      (ts, 0 if alert.once else 1, alert.id, self.uid))
            c.execute("INSERT INTO alert_log(user_id, alert_id, symbol, message, triggered_at) VALUES (?,?,?,?,?)",
                      (self.uid, alert.id, alert.symbol, message, ts))

    def alert_log(self, limit: int = 50) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM alert_log WHERE user_id=? ORDER BY id DESC LIMIT ?",
                                               (self.uid, limit))]

    # --- Benutzer --------------------------------------------------------------
    def user_count(self) -> int:
        with self._conn() as c:
            return int(c.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def create_user(self, username: str, password_hash: str, is_admin: bool | None = None) -> int:
        """Der erste Nutzer wird automatisch Admin (Besitzer)."""
        with self._conn() as c:
            first = c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            cur = c.execute(
                "INSERT INTO users(username, password_hash, created_at, is_admin) VALUES (?,?,?,?)",
                (username, password_hash, now_iso(), int(first if is_admin is None else is_admin)),
            )
            return int(cur.lastrowid)

    def get_user(self, user_id: int | None = None, username: str | None = None) -> dict | None:
        with self._conn() as c:
            if user_id is not None:
                row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            else:
                row = c.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
            return dict(row) if row else None

    def users(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT id, username, is_admin, created_at FROM users ORDER BY id")]

    def admin(self) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM users WHERE is_admin=1 ORDER BY id LIMIT 1").fetchone()
            return dict(row) if row else None

    def set_password(self, user_id: int, password_hash: str, username: str | None = None) -> None:
        """Neues Passwort; erhöht token_version, damit alte Anmeldungen ungültig werden."""
        with self._conn() as c:
            c.execute("UPDATE users SET password_hash=?, token_version=token_version+1, username=COALESCE(?, username) "
                      "WHERE id=?", (password_hash, username, user_id))

    def reset_admin_login(self) -> bool:
        """Notfall (Terminal): Admin-Passwort löschen. Die Oberfläche fragt dann nach neuen Zugangsdaten;
        alle Daten bleiben erhalten."""
        with self._conn() as c:
            return c.execute("UPDATE users SET password_hash='', token_version=token_version+1 "
                             "WHERE id=(SELECT MIN(id) FROM users WHERE is_admin=1)").rowcount > 0

    def delete_user(self, user_id: int) -> bool:
        """Nutzer samt allen seinen Daten löschen (nicht den Admin)."""
        with self._conn() as c:
            row = c.execute("SELECT is_admin FROM users WHERE id=?", (user_id,)).fetchone()
            if not row or row["is_admin"]:
                return False
            for t in ("watchlist", "alerts", "positions", "paper_state", "paper_positions", "paper_trades", "paper_equity",
                      "paper_orders", "alert_log", "user_settings", "chart_layouts", "reports"):
                c.execute(f"DELETE FROM {t} WHERE user_id=?", (user_id,))
            c.execute("DELETE FROM users WHERE id=?", (user_id,))
            return True

    # --- Einladungen ---------------------------------------------------------
    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def create_invite(self, created_by: int, note: str = "", days: int = 7) -> str:
        """Gibt den Einladungscode einmalig zurück; gespeichert wird nur sein Hash."""
        token = secrets.token_urlsafe(24)
        now = datetime.now(timezone.utc)
        with self._conn() as c:
            c.execute("INSERT INTO invites(token_hash, note, created_by, created_at, expires_at) VALUES (?,?,?,?,?)",
                      (self._hash(token), note, created_by, now.isoformat(timespec="seconds"),
                       (now + timedelta(days=days)).isoformat(timespec="seconds")))
        return token

    def invites(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT i.id, i.note, i.created_at, i.expires_at, i.used_at, u.username AS used_by_name "
                             "FROM invites i LEFT JOIN users u ON u.id=i.used_by ORDER BY i.id DESC").fetchall()
            return [dict(r) for r in rows]

    def check_invite(self, token: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM invites WHERE token_hash=?", (self._hash(token),)).fetchone()
        if not row or row["used_by"] or row["expires_at"] < now_iso():
            return None
        return dict(row)

    def use_invite(self, token: str, user_id: int) -> bool:
        with self._conn() as c:
            return c.execute("UPDATE invites SET used_by=?, used_at=? WHERE token_hash=? AND used_by IS NULL",
                             (user_id, now_iso(), self._hash(token))).rowcount > 0

    def delete_invite(self, invite_id: int) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM invites WHERE id=?", (invite_id,)).rowcount > 0

    # --- Einstellungen ---------------------------------------------------------
    def app_settings(self) -> dict[str, str]:
        """Server-weite Einstellungen (nur Admin)."""
        with self._conn() as c:
            return {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM app_settings")}

    def set_app_setting(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO app_settings(key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                      (key, value))

    def delete_app_setting(self, key: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM app_settings WHERE key=?", (key,))

    def user_settings(self) -> dict[str, str]:
        with self._conn() as c:
            return {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM user_settings WHERE user_id=?", (self.uid,))}

    def set_user_setting(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO user_settings(user_id, key, value) VALUES (?,?,?) "
                      "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value", (self.uid, key, value))

    # --- Morgenberichte (die letzten 30 je Nutzer) -----------------------------
    # --- Protokoll der Hintergrund-Jobs (für alle Nutzer, sichtbar in der Administration) --------------------
    def job_start(self, job: str) -> int:
        with self._conn() as c:
            jid = int(c.execute("INSERT INTO job_runs(user_id, job, started_at, status) VALUES (?,?,?,'running')",
                                (self.uid, job, now_iso())).lastrowid)
            c.execute("DELETE FROM job_runs WHERE id NOT IN (SELECT id FROM job_runs ORDER BY id DESC LIMIT 200)")
            return jid

    def job_finish(self, jid: int, status: str, detail: str = "") -> None:
        with self._conn() as c:
            c.execute("UPDATE job_runs SET finished_at=?, status=?, detail=? WHERE id=?",
                      (now_iso(), status, detail[:500], jid))

    def job_runs(self, limit: int = 40) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT j.*, u.username FROM job_runs j LEFT JOIN users u ON u.id = j.user_id ORDER BY j.id DESC LIMIT ?",
                (limit,))]

    def ran_since(self, job: str, since_iso: str) -> bool:
        """Lief der Job für diesen Nutzer seit dem Zeitpunkt (oder gibt es seitdem einen gespeicherten Bericht)?"""
        with self._conn() as c:
            if c.execute("SELECT 1 FROM job_runs WHERE user_id=? AND job=? AND started_at>=? LIMIT 1",
                         (self.uid, job, since_iso)).fetchone():
                return True
            return bool(job.endswith("_report") and c.execute(
                "SELECT 1 FROM reports WHERE user_id=? AND created_at>=? LIMIT 1", (self.uid, since_iso)).fetchone())

    def save_report(self, data: dict) -> int:
        with self._conn() as c:
            rid = int(c.execute("INSERT INTO reports(user_id, created_at, data) VALUES (?,?,?)",
                                (self.uid, now_iso(), json.dumps(data))).lastrowid)
            c.execute("DELETE FROM reports WHERE user_id=? AND id NOT IN "
                      "(SELECT id FROM reports WHERE user_id=? ORDER BY id DESC LIMIT 30)", (self.uid, self.uid))
            return rid

    def get_report(self, report_id: int | None = None) -> dict | None:
        """Bestimmter Bericht oder (ohne id) der neueste."""
        with self._conn() as c:
            if report_id is None:
                row = c.execute("SELECT * FROM reports WHERE user_id=? ORDER BY id DESC LIMIT 1", (self.uid,)).fetchone()
            else:
                row = c.execute("SELECT * FROM reports WHERE user_id=? AND id=?", (self.uid, report_id)).fetchone()
        return {"id": row["id"], "sent_at": row["created_at"], **json.loads(row["data"])} if row else None

    # --- Chart-Arbeitsplatz ----------------------------------------------------
    def chart_layout(self, symbol: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT data, updated_at FROM chart_layouts WHERE user_id=? AND symbol=?",
                            (self.uid, symbol.upper())).fetchone()
        if not row:
            return None
        try:
            return {**json.loads(row["data"]), "updated_at": row["updated_at"]}
        except ValueError:
            return None

    def save_chart_layout(self, symbol: str, data: dict) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO chart_layouts(user_id, symbol, data, updated_at) VALUES (?,?,?,?) "
                      "ON CONFLICT(user_id, symbol) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                      (self.uid, symbol.upper(), json.dumps(data), now_iso()))

    def chart_layouts(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT symbol, updated_at FROM chart_layouts WHERE user_id=? "
                                               "ORDER BY updated_at DESC", (self.uid,))]

    def delete_chart_layout(self, symbol: str) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM chart_layouts WHERE user_id=? AND symbol=?",
                             (self.uid, symbol.upper())).rowcount > 0

    # --- Positionen (erfasste Käufe) -----------------------------------------
    POSITION_FIELDS = ("symbol", "quantity", "buy_price", "buy_date", "fees", "currency", "stop", "target", "note",
                       "sell_price", "sell_date", "sell_fees", "trail_pct", "watch_state", "buy_time", "sell_time")

    def positions(self, symbol: str | None = None, open_only: bool = False) -> list[dict]:
        q, args = "SELECT * FROM positions WHERE user_id=?", [self.uid]
        if symbol:
            q += " AND symbol=?"
            args.append(symbol.upper())
        if open_only:
            q += " AND sell_date IS NULL"
        with self._conn() as c:
            return [dict(r) for r in c.execute(q + " ORDER BY buy_date, id", args)]

    def get_position(self, pos_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM positions WHERE id=? AND user_id=?", (pos_id, self.uid)).fetchone()
            return dict(row) if row else None

    def add_position(self, data: dict) -> int:
        cols = [k for k in self.POSITION_FIELDS if k in data]
        vals = [data[k].upper() if k == "symbol" else data[k] for k in cols]
        with self._conn() as c:
            cur = c.execute(
                f"INSERT INTO positions(user_id, {', '.join(cols)}, created_at) VALUES (?, {', '.join('?' * len(cols))}, ?)",
                (self.uid, *vals, now_iso()),
            )
            return int(cur.lastrowid)

    def update_position(self, pos_id: int, data: dict) -> bool:
        cols = [k for k in self.POSITION_FIELDS if k in data and k != "symbol"]
        if not cols:
            return self.get_position(pos_id) is not None
        with self._conn() as c:
            return c.execute(f"UPDATE positions SET {', '.join(f'{k}=?' for k in cols)} WHERE id=? AND user_id=?",
                             (*[data[k] for k in cols], pos_id, self.uid)).rowcount > 0

    def remove_position(self, pos_id: int) -> bool:
        with self._conn() as c:
            return c.execute("DELETE FROM positions WHERE id=? AND user_id=?", (pos_id, self.uid)).rowcount > 0

    # --- Schattendepot -------------------------------------------------------
    def paper_state(self) -> dict[str, str]:
        with self._conn() as c:
            return {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM paper_state WHERE user_id=?", (self.uid,))}

    def set_paper_state(self, **values) -> None:
        with self._conn() as c:
            for k, v in values.items():
                c.execute("INSERT INTO paper_state(user_id, key, value) VALUES (?,?,?) "
                          "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value", (self.uid, k, str(v)))

    def paper_positions(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM paper_positions WHERE user_id=? ORDER BY entry_day, symbol",
                                               (self.uid,))]

    def save_paper_position(self, pos: dict) -> None:
        cols = ("symbol", "shares", "entry", "entry_day", "cost", "stop", "target", "checked_day", "reason")
        with self._conn() as c:
            c.execute(f"INSERT OR REPLACE INTO paper_positions(user_id, {', '.join(cols)}) "
                      f"VALUES (?, {', '.join('?' * len(cols))})", (self.uid, *[pos.get(k) for k in cols]))

    def remove_paper_position(self, symbol: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM paper_positions WHERE user_id=? AND symbol=?", (self.uid, symbol))

    def add_paper_trade(self, t: dict) -> None:
        cols = ("symbol", "side", "shares", "price", "fee", "day", "reason", "pl", "pl_pct")
        with self._conn() as c:
            c.execute(f"INSERT INTO paper_trades(user_id, {', '.join(cols)}, created_at) "
                      f"VALUES (?, {', '.join('?' * len(cols))}, ?)", (self.uid, *[t.get(k) for k in cols], now_iso()))

    def paper_trades(self, limit: int = 500) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM paper_trades WHERE user_id=? ORDER BY id DESC LIMIT ?",
                                               (self.uid, limit))]

    def add_paper_order(self, o: dict) -> int:
        cols = ("symbol", "side", "kind", "limit_price", "stop", "target", "ref_price", "reason", "day")
        with self._conn() as c:
            return int(c.execute(f"INSERT INTO paper_orders(user_id, {', '.join(cols)}, created_at) "
                                 f"VALUES (?, {', '.join('?' * len(cols))}, ?)",
                                 (self.uid, *[o.get(k) for k in cols], now_iso())).lastrowid)

    def paper_orders(self, status: str | None = None, limit: int = 100) -> list[dict]:
        q, args = "SELECT * FROM paper_orders WHERE user_id=?", [self.uid]
        if status:
            q += " AND status=?"
            args.append(status)
        with self._conn() as c:
            return [dict(r) for r in c.execute(q + " ORDER BY id DESC LIMIT ?", (*args, limit))]

    def close_paper_order(self, order_id: int, status: str, note: str = "") -> None:
        with self._conn() as c:
            c.execute("UPDATE paper_orders SET status=?, note=?, done_at=? WHERE id=? AND user_id=?",
                      (status, note, now_iso(), order_id, self.uid))

    def set_paper_equity(self, day: str, equity: float, cash: float) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO paper_equity(user_id, day, equity, cash) VALUES (?,?,?,?)",
                      (self.uid, day, equity, cash))

    def paper_equity(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT day, equity, cash FROM paper_equity WHERE user_id=? ORDER BY day",
                                               (self.uid,))]

    def reset_paper(self) -> None:
        with self._conn() as c:
            for t in ("paper_positions", "paper_trades", "paper_equity", "paper_orders"):
                c.execute(f"DELETE FROM {t} WHERE user_id=?", (self.uid,))
            c.execute("DELETE FROM paper_state WHERE user_id=? AND key != 'backtest'", (self.uid,))
