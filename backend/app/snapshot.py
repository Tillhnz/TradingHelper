"""Vorberechnete Ergebnisse für schnelle Seiten.

* technical(): Analyse + Einschätzung eines Werts. Das Ergebnis wird wiederverwendet, solange sich die Kursdaten nicht
  geändert haben (Fingerabdruck aus Länge, letztem Tag und letztem Kurs) – Übersicht, Depot und Bericht rechnen
  denselben Wert also nur einmal.
* overview(): Zeilen der Übersicht/Watchlist mit Zeitbudget. Was innerhalb des Budgets (Standard 1,5 s) nicht fertig
  wird, kommt als letzter bekannter Stand bzw. als „lädt“ zurück und wird im Hintergrund weitergerechnet; die
  Oberfläche fragt dann kurz darauf noch einmal nach. So dauert keine Seite länger als etwa zwei Sekunden.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

import pandas as pd

from . import analysis, entry, market

log = logging.getLogger(__name__)

_TECH: dict[tuple, tuple[tuple, float, object]] = {}
_TECH_LOCK = threading.Lock()
_TECH_MAX = 4000

_ROWS: dict[tuple, tuple[float, dict]] = {}
_ROWS_LOCK = threading.Lock()
ROW_TTL = 45  # Sekunden; danach wird neu gerechnet (aus dem Kursspeicher, also schnell)

_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="snapshot")
_RUNNING: dict[tuple, object] = {}


def clear() -> None:
    with _TECH_LOCK:
        _TECH.clear()
    with _ROWS_LOCK:
        _ROWS.clear()
        _RUNNING.clear()


def _profile_key(profile: analysis.Profile) -> tuple:
    return (profile.horizon, profile.risk, getattr(profile, "portfolio_size", 0))


def _fingerprint(df: pd.DataFrame) -> tuple:
    if df is None or df.empty:
        return (0,)
    return (len(df), str(df.index[-1]), round(float(df["close"].iloc[-1]), 6), round(float(df["close"].iloc[0]), 6),
            round(float(df["high"].iloc[-1]), 6))


def technical(symbol: str, profile: analysis.Profile, currency: str | None = None, period: str | None = None):
    """(df, analysis, recommendation ohne News) – zwischengespeichert, solange die Kurse gleich bleiben."""
    df = market.get_history(symbol, period or profile.period, "1d", currency=currency)
    key = (symbol.upper(), _profile_key(profile), currency, period or profile.period)
    fp = _fingerprint(df)
    with _TECH_LOCK:
        hit = _TECH.get(key)
    if hit and hit[0] == fp:
        a, rec = hit[2]
        return df, _copy(a), dataclasses.replace(rec)
    a = analysis.analyze(symbol, df, profile)
    rec = analysis.recommend(a, None, profile)
    with _TECH_LOCK:
        if len(_TECH) > _TECH_MAX:
            _TECH.clear()
        _TECH[key] = (fp, time.time(), (a, rec))
    return df, _copy(a), dataclasses.replace(rec)


def _copy(a: analysis.Analysis) -> analysis.Analysis:
    """Eigene Kopie für den Aufrufer: recommend() mit News ergänzt breakout – das soll den Speicher nicht verändern."""
    return dataclasses.replace(a, breakout=dict(a.breakout) if a.breakout else None, metrics=dict(a.metrics),
                               signals=list(a.signals))


def _since_pct(df: pd.DataFrame, added_at: str | None) -> float | None:
    """Veränderung seit dem Hinzufügen zur Watchlist (für die Sortierung „Veränderung gesamt“ bei Werten ohne Bestand)."""
    if df is None or df.empty or not added_at:
        return None
    try:
        start = pd.Timestamp(str(added_at)[:10])
        idx = df.index.tz_localize(None) if getattr(df.index, "tz", None) is not None else df.index
        pos = int(idx.searchsorted(start))
        base = float(df["close"].iloc[min(pos, len(df) - 1)])
        return round((float(df["close"].iloc[-1]) / base - 1) * 100, 2) if base else None
    except Exception:  # noqa: BLE001
        return None


def compute_row(w: dict, profile: analysis.Profile, target: str | None) -> dict:
    """Eine Zeile der Übersicht (ohne Bestand, ohne News)."""
    sym = w["symbol"]
    row = {"symbol": sym, "ticker": w.get("ticker"), "note": w.get("note", ""), "name": w.get("name"),
           "exchange": w.get("exchange"), "native_currency": w.get("currency"),
           "currency": market.shown_currency(w.get("currency"), target)}
    try:
        df, a, rec = technical(sym, profile, target)
        spark = [round(float(x), 4) for x in df["close"].tail(30)]
        row.update(price=a.last_close, change_pct=a.change_pct_1d, action=rec.action, score=rec.combined,
                   rsi=a.metrics.get("rsi"), spark=spark, entry=entry.plan(a, rec, currency=row["currency"])["summary"],
                   breakout=a.breakout, as_of=int(pd.Timestamp(df.index[-1]).timestamp()),
                   since_pct=_since_pct(df, w.get("added_at")))
    except Exception as exc:  # noqa: BLE001
        row["error"] = str(exc)
    return row


def _row_key(sym: str, profile: analysis.Profile, target: str | None) -> tuple:
    return (sym.upper(), _profile_key(profile), target)


def _run_row(key: tuple, w: dict, profile: analysis.Profile, target: str | None) -> dict:
    try:
        row = compute_row(w, profile, target)
        with _ROWS_LOCK:
            _ROWS[key] = (time.time(), row)
        return row
    finally:
        with _ROWS_LOCK:
            _RUNNING.pop(key, None)


def overview(watch: list[dict], profile: analysis.Profile, target: str | None, budget: float | None = 1.5) -> list[dict]:
    """Zeilen für alle Werte. budget=None wartet auf alle (Hintergrund-Jobs)."""
    now = time.time()
    out: list[dict | None] = [None] * len(watch)
    futures = {}
    for i, w in enumerate(watch):
        key = _row_key(w["symbol"], profile, target)
        with _ROWS_LOCK:
            hit = _ROWS.get(key)
            fut = _RUNNING.get(key)
        if hit and now - hit[0] < ROW_TTL:
            out[i] = {**hit[1], "note": w.get("note", hit[1].get("note", ""))}
            continue
        if fut is None:
            fut = _POOL.submit(_run_row, key, w, profile, target)
            with _ROWS_LOCK:
                _RUNNING[key] = fut
        futures[fut] = (i, key, w)
    if futures:
        done, _ = wait(list(futures), timeout=budget)
        for fut, (i, key, w) in futures.items():
            if fut in done:
                try:
                    out[i] = {**fut.result(), "note": w.get("note", "")}
                    continue
                except Exception as exc:  # noqa: BLE001
                    out[i] = {"symbol": w["symbol"], "name": w.get("name"), "error": str(exc)}
                    continue
            with _ROWS_LOCK:
                hit = _ROWS.get(key)
            if hit:  # letzter bekannter Stand, wird gerade aktualisiert
                out[i] = {**hit[1], "note": w.get("note", ""), "refreshing": True}
            else:
                out[i] = {"symbol": w["symbol"], "ticker": w.get("ticker"), "name": w.get("name"), "note": w.get("note", ""),
                          "exchange": w.get("exchange"), "native_currency": w.get("currency"),
                          "currency": market.shown_currency(w.get("currency"), target), "pending": True}
    return [r for r in out if r is not None]
