"""Hintergrunddienst, der alle Daten vorhält, damit die Oberfläche nie auf Kursquellen warten muss.

Takt (alles im Hintergrund, Fehler einzelner Werte stoppen nichts):
* alle 20 s (Handelszeit) bzw. 10 min (nachts/Wochenende): aktuelle Kurse aller beobachteten, gehaltenen und auf der
  Startseite gezeigten Werte → Quote-Speicher
* alle 10 min: Tageskerzen nachladen, danach die Übersicht jedes Nutzers vorberechnen
* alle 15 min: Nachrichten zu den Werten aufwärmen
* alle 30 min: Social-Stimmung, alle 6 h: Makrozahlen
Nachts trainiert scheduler.py zusätzlich das Modell (brain.py).
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

from . import analysis, market, settings_store, snapshot
from .config import Settings
from .storage import Storage

log = logging.getLogger(__name__)

_THREAD: threading.Thread | None = None
_STOP = threading.Event()
STATUS: dict = {"running": False, "cycles": {}, "errors": {}, "tracked": 0}


def trading_time(now: datetime | None = None) -> bool:
    """Grob: werktags 7:30–22:30 Uhr deutscher Zeit (gettex 8–22, Xetra, US-Handel bis 22 Uhr)."""
    now = now or datetime.now(ZoneInfo("Europe/Berlin"))
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 7 * 60 + 30 <= minutes <= 22 * 60 + 30


def quote_interval() -> float:
    return 20 if trading_time() else 600


def tracked_symbols(storage: Storage) -> list[str]:
    syms = set(storage.all_tracked_symbols())
    try:
        from . import macro

        syms.update(macro.MARKET_SYMBOLS)
    except Exception:  # noqa: BLE001
        pass
    if syms - set(_market_only()):  # Vergleichs-ETFs der Analyse nur, wenn es eigene Werte gibt
        from .performance import BENCH_SYMBOLS

        syms.update(BENCH_SYMBOLS)
    return sorted(syms)


def _market_only() -> list[str]:
    try:
        from . import macro

        return list(macro.MARKET_SYMBOLS)
    except Exception:  # noqa: BLE001
        return []


def _mark(name: str, started: float, n: int | None = None, error: str | None = None) -> None:
    STATUS["cycles"][name] = {"at": time.time(), "seconds": round(time.time() - started, 2), "count": n}
    if error:
        STATUS["errors"][name] = {"at": time.time(), "error": error[:300]}


def refresh_quotes(symbols: list[str], workers: int = 4) -> int:
    ok = 0

    def one(sym):
        try:
            market.fetch_live(sym)
            return True
        except Exception as exc:  # noqa: BLE001
            log.debug("Kurs %s: %s", sym, exc)
            return False

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="quotes") as pool:
        for r in pool.map(one, symbols):
            ok += bool(r)
    return ok


def refresh_daily(symbols: list[str], workers: int = 3) -> int:
    ok = 0

    def one(sym):
        try:
            market.refresh_daily(sym)
            return True
        except Exception as exc:  # noqa: BLE001
            log.debug("Tageskerzen %s: %s", sym, exc)
            return False

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="daily") as pool:
        for r in pool.map(one, symbols):
            ok += bool(r)
    return ok


def warm_users(storage: Storage, base: Settings) -> int:
    """Übersicht und Depot jedes Nutzers vorberechnen (füllt die Zwischenspeicher von snapshot.py)."""
    from . import portfolio

    n = 0
    for u in storage.users():
        st = storage.for_user(u["id"])
        cfg = settings_store.for_user(st, base)
        profile = analysis.profile_from(cfg)
        target = None if cfg.display_currency == "native" else cfg.display_currency
        watch = st.watchlist()
        snapshot.overview(watch, profile, target, budget=None)
        for p in st.positions(open_only=True):
            try:
                portfolio.evaluate(p, profile)
            except Exception:  # noqa: BLE001
                pass
        n += len(watch)
    return n


def warm_news(storage: Storage, base: Settings) -> int:
    from . import news

    n = 0
    seen: set[str] = set()
    for u in storage.users():
        st = storage.for_user(u["id"])
        cfg = settings_store.for_user(st, base)
        for w in st.watchlist()[:40]:
            if w["symbol"] in seen:
                continue
            seen.add(w["symbol"])
            try:
                news.collect(w["symbol"], cfg, w.get("name"), limit=12)
                n += 1
            except Exception:  # noqa: BLE001
                pass
        try:
            news.market_news(cfg, limit=40)
        except Exception:  # noqa: BLE001
            pass
    return n


def run_cycle(storage: Storage, base: Settings, state: dict) -> None:
    """Ein Durchgang: macht nur, was fällig ist."""
    now = time.time()
    syms = tracked_symbols(storage)
    STATUS["tracked"] = len(syms)
    jobs = [
        ("quotes", quote_interval(), lambda: refresh_quotes(syms)),
        ("daily", 600, lambda: refresh_daily(syms)),
        ("overview", 600, lambda: warm_users(storage, base)),
        ("news", 480, lambda: warm_news(storage, base)),
        ("social", 1800, lambda: _social(storage, syms)),
        ("macro", 6 * 3600, _macro),
    ]
    for name, every, fn in jobs:
        if _STOP.is_set():
            return
        if now - state.get(name, 0) < every:
            continue
        state[name] = time.time()
        t0 = time.time()
        try:
            _mark(name, t0, fn())
        except Exception as exc:  # noqa: BLE001
            log.exception("Hintergrund-Aktualisierung %s fehlgeschlagen", name)
            _mark(name, t0, error=f"{type(exc).__name__}: {exc}")


def _social(storage: Storage, syms: list[str]) -> int:
    from . import social

    return social.refresh(storage, syms)


def _macro() -> int:
    from . import macro

    return macro.refresh()


def _loop(storage: Storage, base: Settings) -> None:
    state: dict = {}
    STATUS["running"] = True
    # kurz warten, damit der Start der API nicht ausgebremst wird
    if _STOP.wait(3):
        return
    while not _STOP.is_set():
        try:
            run_cycle(storage, base, state)
        except Exception:  # noqa: BLE001
            log.exception("Hintergrunddienst")
        _STOP.wait(5)
    STATUS["running"] = False


def start(storage: Storage, base: Settings) -> None:
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(target=_loop, args=(storage, base), daemon=True, name="refresher")
    _THREAD.start()


def stop() -> None:
    _STOP.set()


def status() -> dict:
    from . import marketstore

    st = marketstore.get_store()
    return {**STATUS, "trading_time": trading_time(), "quote_interval": quote_interval(),
            "store": st.stats() if st else None}
