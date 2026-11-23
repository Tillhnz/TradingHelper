"""Dauerhafter Kursspeicher (eigene SQLite-Datei data/market.db, darf jederzeit gelöscht werden).

Warum: Früher wurde bei jedem Seitenaufruf die komplette Historie jedes Werts frisch bei Yahoo bzw. onvista geholt –
nacheinander, nur im Arbeitsspeicher zwischengespeichert und nach jedem Neustart wieder leer. Das hat Seiten wie die
Übersicht 10–60 Sekunden gekostet. Jetzt gilt:

* Tageskerzen liegen dauerhaft hier. Beim ersten Mal werden 5 Jahre geholt, danach nur noch die letzten Tage
  (inkrementell). Jeder Zeitraum bis 5 Jahre kommt danach ohne Netzwerk aus dem Speicher.
* Aktuelle Kurse (Quotes) schreibt der Hintergrunddienst (refresher.py) laufend hier hinein. Die Oberfläche liest
  nur noch – Antwortzeiten im Millisekundenbereich.
* Dazu ein allgemeiner Zwischenspeicher (kv) für Stammdaten, Makrozahlen, Social-Stimmung und vorberechnete
  Ergebnisse, damit nach einem Neustart sofort wieder alles da ist.

Alle Zugriffe sind thread-sicher (eigene Verbindung pro Aufruf, WAL-Modus für gleichzeitiges Lesen und Schreiben).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    symbol TEXT NOT NULL,
    day TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL NOT NULL, volume REAL,
    PRIMARY KEY (symbol, day)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS series (
    symbol TEXT PRIMARY KEY,
    first_day TEXT, last_day TEXT,
    span_days INTEGER NOT NULL DEFAULT 0,
    fetched_at REAL NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS quotes (
    symbol TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    fetched_at REAL NOT NULL
);
"""


class MarketStore:
    def __init__(self, path: Path | str):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---------- Tageskerzen ----------

    def series(self, symbol: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM series WHERE symbol=?", (symbol.upper(),)).fetchone()
        return dict(row) if row else None

    def daily(self, symbol: str, start: str | None = None) -> pd.DataFrame:
        """Tageskerzen ab `start` (YYYY-MM-DD), Index = Tag (ohne Zeitzone)."""
        q, args = "SELECT day, open, high, low, close, volume FROM candles WHERE symbol=?", [symbol.upper()]
        if start:
            q += " AND day>=?"
            args.append(start)
        with self._conn() as c:
            rows = c.execute(q + " ORDER BY day", args).fetchall()
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"], dtype=float)
        df = pd.DataFrame([tuple(r) for r in rows], columns=["day", "open", "high", "low", "close", "volume"])
        df.index = pd.DatetimeIndex(pd.to_datetime(df.pop("day")))
        df.index.name = None
        return df.astype(float)

    def put_daily(self, symbol: str, df: pd.DataFrame, span_days: int | None = None, source: str = "",
                  replace_from: str | None = None) -> int:
        """Kerzen speichern (vorhandene Tage werden überschrieben). Mit replace_from werden alle Tage ab diesem Datum
        vorher gelöscht (z. B. wenn die Quelle nachträglich korrigiert hat)."""
        sym = symbol.upper()
        if df is None or df.empty:
            rows = []
        else:
            days = _day_strings(df.index)
            d = df.reindex(columns=["open", "high", "low", "close", "volume"])
            rows = [
                (sym, day, _f(o), _f(h), _f(lo), float(cl), _f(v) or 0.0)
                for day, o, h, lo, cl, v in zip(days, d["open"], d["high"], d["low"], d["close"], d["volume"],
                                                strict=True)
                if cl == cl  # NaN raus
            ]
        with self._conn() as c:
            if replace_from:
                c.execute("DELETE FROM candles WHERE symbol=? AND day>=?", (sym, replace_from))
            c.executemany("INSERT OR REPLACE INTO candles(symbol, day, open, high, low, close, volume) "
                          "VALUES (?,?,?,?,?,?,?)", rows)
            first, last = c.execute("SELECT MIN(day), MAX(day) FROM candles WHERE symbol=?", (sym,)).fetchone()
            old = c.execute("SELECT span_days FROM series WHERE symbol=?", (sym,)).fetchone()
            span = max(int(span_days or 0), int(old[0]) if old else 0)
            c.execute("INSERT INTO series(symbol, first_day, last_day, span_days, fetched_at, source) VALUES (?,?,?,?,?,?) "
                      "ON CONFLICT(symbol) DO UPDATE SET first_day=excluded.first_day, last_day=excluded.last_day, "
                      "span_days=excluded.span_days, fetched_at=excluded.fetched_at, source=excluded.source",
                      (sym, first, last, span, time.time(), source))
        return len(rows)

    def touch(self, symbol: str) -> None:
        """Abruf ohne neue Daten (z. B. Wochenende): trotzdem als frisch markieren."""
        with self._conn() as c:
            c.execute("UPDATE series SET fetched_at=? WHERE symbol=?", (time.time(), symbol.upper()))

    def symbols(self) -> list[str]:
        with self._conn() as c:
            return [r[0] for r in c.execute("SELECT symbol FROM series ORDER BY symbol")]

    def drop(self, symbol: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM candles WHERE symbol=?", (symbol.upper(),))
            c.execute("DELETE FROM series WHERE symbol=?", (symbol.upper(),))

    # ---------- Aktuelle Kurse ----------

    def put_quote(self, symbol: str, data: dict) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO quotes(symbol, data, fetched_at) VALUES (?,?,?)",
                      (symbol.upper(), json.dumps(data), time.time()))

    def quote(self, symbol: str) -> tuple[dict, float] | None:
        with self._conn() as c:
            row = c.execute("SELECT data, fetched_at FROM quotes WHERE symbol=?", (symbol.upper(),)).fetchone()
        return (json.loads(row["data"]), float(row["fetched_at"])) if row else None

    def quotes(self, symbols: list[str]) -> dict[str, tuple[dict, float]]:
        if not symbols:
            return {}
        syms = [s.upper() for s in symbols]
        with self._conn() as c:
            rows = c.execute(f"SELECT symbol, data, fetched_at FROM quotes WHERE symbol IN ({','.join('?' * len(syms))})",
                             syms).fetchall()
        return {r["symbol"]: (json.loads(r["data"]), float(r["fetched_at"])) for r in rows}

    # ---------- Allgemeiner Zwischenspeicher ----------

    def put(self, key: str, data: Any) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO kv(key, data, fetched_at) VALUES (?,?,?)",
                      (key, json.dumps(data, default=_json_default), time.time()))

    def get(self, key: str, max_age: float | None = None) -> Any:
        hit = self.get_with_age(key)
        if hit is None:
            return None
        data, age = hit
        if max_age is not None and age > max_age:
            return None
        return data

    def get_with_age(self, key: str) -> tuple[Any, float] | None:
        with self._conn() as c:
            row = c.execute("SELECT data, fetched_at FROM kv WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        return json.loads(row["data"]), time.time() - float(row["fetched_at"])

    def keys(self, prefix: str) -> list[str]:
        with self._conn() as c:
            return [r[0] for r in c.execute("SELECT key FROM kv WHERE key LIKE ? ORDER BY key", (prefix + "%",))]

    def delete(self, key: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM kv WHERE key=?", (key,))

    def stats(self) -> dict:
        with self._conn() as c:
            n_c = c.execute("SELECT COUNT(*) FROM candles").fetchone()[0]
            n_s = c.execute("SELECT COUNT(*) FROM series").fetchone()[0]
            n_q = c.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
            n_k = c.execute("SELECT COUNT(*) FROM kv").fetchone()[0]
        size = Path(self.path).stat().st_size if Path(self.path).exists() else 0
        return {"candles": n_c, "symbols": n_s, "quotes": n_q, "cached": n_k, "bytes": size}


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else v


def _json_default(o):
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if hasattr(o, "item"):
        return o.item()
    raise TypeError(f"nicht speicherbar: {type(o).__name__}")


def _day_strings(idx) -> list[str]:
    """Kalendertag jeder Kerze in Ortszeit der Börse (gettex-Kerzen beginnen um 23 Uhr UTC des Vortags)."""
    di = pd.DatetimeIndex(idx)
    if di.tz is not None:
        di = di.tz_localize(None)
    return [d.strftime("%Y-%m-%d") for d in di.normalize()]


# ---------- Ein Speicher pro Prozess ----------

_STORE: MarketStore | None = None
_LOCK = threading.Lock()


def get_store() -> MarketStore | None:
    return _STORE


def open_store(path: Path | str) -> MarketStore:
    global _STORE
    with _LOCK:
        if _STORE is None or _STORE.path != str(path):
            _STORE = MarketStore(path)
        return _STORE


def close_store() -> None:
    global _STORE
    with _LOCK:
        _STORE = None
