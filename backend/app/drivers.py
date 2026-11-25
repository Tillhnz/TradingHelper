"""Warum läuft ein Wert gerade so, wie er läuft?

Drei Zutaten, alle mit Daten statt Vermutungen:
1. Zerlegung der Kursänderung in Markt, Branche und Eigenes. Über ein Jahr Tagesrenditen wird geschätzt, wie stark
   der Wert mit seinem Heimatmarkt (z. B. DAX) und seiner Branche (US-Branchen-ETF) mitschwingt
   (Regression auf Markt und Branche-minus-Markt). Was die beiden nicht erklären, ist unternehmensspezifisch.
2. Die größten Ausschläge der letzten drei Monate mit den Schlagzeilen genau dieser Tage (Google News, Datumsfilter).
3. Die aktuelle Nachrichtenlage (wie auf der Seite des Werts) und der Abstand zum Jahreshoch/-tief.

Ergebnis wird je Wert 30 Minuten zwischengespeichert; der erste Abruf läuft im Hintergrund (pending)."""

from __future__ import annotations

import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import timedelta

import numpy as np
import pandas as pd

from . import gettex, market, marketstore, news

log = logging.getLogger(__name__)

TTL = 30 * 60
CALC_VERSION = 2
WINDOWS = [("Woche", 5), ("Monat", 21), ("3 Monate", 63), ("1 Jahr", 252)]

# Heimatmarkt je Land (ISIN-Präfix bzw. Land aus den Stammdaten)
INDEX_BY_COUNTRY = {
    "DE": ("^GDAXI", "DAX"), "AT": ("^GDAXI", "DAX"),
    "US": ("^GSPC", "S&P 500"), "CA": ("^GSPC", "S&P 500"),
    "FR": ("^STOXX50E", "Euro Stoxx 50"), "NL": ("^STOXX50E", "Euro Stoxx 50"), "IT": ("^STOXX50E", "Euro Stoxx 50"),
    "ES": ("^STOXX50E", "Euro Stoxx 50"), "BE": ("^STOXX50E", "Euro Stoxx 50"), "FI": ("^STOXX50E", "Euro Stoxx 50"),
    "IE": ("^STOXX50E", "Euro Stoxx 50"), "PT": ("^STOXX50E", "Euro Stoxx 50"), "LU": ("^STOXX50E", "Euro Stoxx 50"),
    "DK": ("^STOXX50E", "Euro Stoxx 50"), "SE": ("^STOXX50E", "Euro Stoxx 50"), "NO": ("^STOXX50E", "Euro Stoxx 50"),
    "CH": ("^SSMI", "SMI"), "GB": ("^FTSE", "FTSE 100"), "JP": ("^N225", "Nikkei 225"), "AU": ("^AXJO", "ASX 200"),
}
COUNTRY_WORDS = {"germany": "DE", "deutschland": "DE", "united states": "US", "usa": "US", "vereinigte staaten": "US",
                 "france": "FR", "frankreich": "FR", "netherlands": "NL", "niederlande": "NL", "switzerland": "CH",
                 "schweiz": "CH", "united kingdom": "GB", "großbritannien": "GB", "japan": "JP", "australia": "AU",
                 "australien": "AU", "canada": "CA", "kanada": "CA", "italy": "IT", "italien": "IT", "spain": "ES",
                 "spanien": "ES", "austria": "AT", "österreich": "AT", "ireland": "IE", "irland": "IE"}
WORLD = ("EUNL.DE", "Weltmarkt (MSCI World)")
SECTOR_NAMES = {"XLK": "Technologie", "XLF": "Finanzen", "XLV": "Gesundheit", "XLE": "Energie", "XLI": "Industrie",
                "XLY": "Zyklischer Konsum", "XLP": "Basiskonsum", "XLU": "Versorger", "XLB": "Grundstoffe",
                "XLRE": "Immobilien", "XLC": "Kommunikation"}

INDEX_CCY = {"^GDAXI": "EUR", "^STOXX50E": "EUR", "^GSPC": "USD", "^SSMI": "CHF", "^FTSE": "GBP", "^N225": "JPY",
             "^AXJO": "AUD", "EUNL.DE": "EUR"}

_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="drivers")
_RUNNING: dict[str, object] = {}
_LOCK = threading.Lock()


def _closes(symbol: str, period: str = "1y") -> pd.Series | None:
    try:
        df = market.get_history(symbol, period, "1d")
    except Exception as exc:  # noqa: BLE001
        log.debug("drivers: keine Kurse %s: %s", symbol, exc)
        return None
    if df is None or df.empty:
        return None
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    s = pd.Series(df["close"].to_numpy(dtype=float), index=idx.normalize())
    return s[~s.index.duplicated(keep="last")].sort_index()


def in_currency(s: pd.Series | None, frm: str | None, to: str | None) -> pd.Series | None:
    """Vergleichsreihe in die Währung des Werts umrechnen – sonst landet die Wechselkursbewegung im „Eigenen“."""
    if s is None or not frm or not to or frm == to:
        return s
    try:
        rates = market.fx_rates(frm, to, "1y")
        rates.index = pd.DatetimeIndex(rates.index).normalize()
        r = rates.reindex(rates.index.union(s.index)).sort_index().ffill().bfill().reindex(s.index)
        return s * r
    except Exception as exc:  # noqa: BLE001
        log.debug("drivers: Umrechnung %s→%s: %s", frm, to, exc)
        return s


def country_of(symbol: str, info: dict) -> str | None:
    if gettex.is_gettex(symbol):
        isin = gettex.isin_of(symbol) or ""
        return isin[:2] if isin else None
    isin = str(info.get("isin") or "")
    if len(isin) == 12:
        return isin[:2].upper()
    c = str(info.get("country") or "").strip().lower()
    if c in COUNTRY_WORDS:
        return COUNTRY_WORDS[c]
    suffix = symbol.rsplit(".", 1)[-1].upper() if "." in symbol else "US"
    return {"DE": "DE", "F": "DE", "PA": "FR", "AS": "NL", "MI": "IT", "MC": "ES", "SW": "CH", "L": "GB", "T": "JP",
            "AX": "AU", "TO": "CA", "VI": "AT", "US": "US"}.get(suffix)


def _ret(s: pd.Series, n: int) -> float | None:
    if s is None or len(s) <= n:
        return None
    a, b = float(s.iloc[-n - 1]), float(s.iloc[-1])
    return (b / a - 1) if a else None


def _fit(stock: pd.Series, mkt: pd.Series | None, sec: pd.Series | None) -> dict:
    """Wie stark schwingt der Wert mit Markt und Branche mit? Tägliche Log-Renditen, ein Jahr."""
    frame = pd.DataFrame({"s": np.log(stock).diff()})
    if mkt is not None:
        frame["m"] = np.log(mkt.reindex(stock.index).ffill()).diff()
    if sec is not None:
        frame["x"] = np.log(sec.reindex(stock.index).ffill()).diff()
    frame = frame.dropna()
    frame = frame[frame.abs().max(axis=1) < 0.5]  # Datenfehler/Splits nicht mitschätzen
    out = {"beta_m": None, "beta_x": None, "r2": None, "n": len(frame)}
    if len(frame) < 60 or "m" not in frame:
        return out
    cols = ["m"]
    if "x" in frame:
        frame["x"] = frame["x"] - frame["m"]  # Branche über den Markt hinaus
        cols.append("x")
    X = np.column_stack([np.ones(len(frame)), *[frame[c].to_numpy() for c in cols]])
    y = frame["s"].to_numpy()
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    fitted = X @ coef
    ss_res = float(((y - fitted) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum()) or 1e-12
    out.update(beta_m=float(coef[1]), beta_x=float(coef[2]) if len(coef) > 2 else None, r2=max(0.0, 1 - ss_res / ss_tot))
    return out


def decompose(stock: pd.Series, mkt: pd.Series | None, sec: pd.Series | None, fit: dict, n: int) -> dict | None:
    """Kursänderung über n Handelstage = Markt-Anteil + Branchen-Anteil + Eigenes (in Prozentpunkten)."""
    total = _ret(stock, n)
    if total is None:
        return None
    out = {"days": n, "total": total * 100, "market_ret": None, "sector_ret": None, "market": None, "sector": None,
           "own": None}
    m = _ret(mkt.reindex(stock.index).ffill(), n) if mkt is not None else None
    x = _ret(sec.reindex(stock.index).ffill(), n) if sec is not None else None
    out["market_ret"] = m * 100 if m is not None else None
    out["sector_ret"] = x * 100 if x is not None else None
    if fit.get("beta_m") is None or m is None:
        return out
    lt = math.log1p(total)
    part_m = fit["beta_m"] * math.log1p(m)
    part_x = fit["beta_x"] * (math.log1p(x) - math.log1p(m)) if fit.get("beta_x") is not None and x is not None else 0.0
    own = lt - part_m - part_x
    # in Prozentpunkte der Gesamtänderung umrechnen (Anteile der Log-Rendite)
    scale = (total * 100) / lt if abs(lt) > 1e-9 else 100.0
    out.update(market=part_m * scale, sector=part_x * scale if x is not None else None, own=own * scale)
    return out


def big_days(stock: pd.Series, mkt: pd.Series | None, n: int = 63, top: int = 4) -> list[dict]:
    """Die stärksten Tagesbewegungen der letzten n Handelstage, die nicht nur der Markt waren."""
    r = stock.pct_change().dropna().iloc[-n:]
    if r.empty:
        return []
    m = mkt.reindex(stock.index).ffill().pct_change().reindex(r.index) if mkt is not None else None
    sd = float(stock.pct_change().dropna().iloc[-252:].std() or 0.02)
    cand = []
    for d, x in r.items():
        mx = float(m.loc[d]) if m is not None and d in m.index and pd.notna(m.loc[d]) else 0.0
        if abs(x) >= max(2.2 * sd, 0.03) and abs(x - mx) >= 0.02:
            cand.append({"day": str(d.date()), "pct": round(x * 100, 1), "market_pct": round(mx * 100, 1)})
    cand.sort(key=lambda c: -abs(c["pct"]))
    return sorted(cand[:top], key=lambda c: c["day"], reverse=True)


def headlines_on(term: str, day: str, limit: int = 3) -> list[dict]:
    """Schlagzeilen rund um einen Tag (Tag davor bis Tag danach) über Google News."""
    if not term:
        return []
    d = pd.Timestamp(day)
    q = f'"{term}" after:{(d - timedelta(days=1)).date()} before:{(d + timedelta(days=2)).date()}'
    items = []
    for lang, word in (("de", "Aktie"), ("en", "stock")):
        try:
            items += news._relevant(news.fetch_feed(news.google_url(f"{q} {word}", lang), "Google News", True), term)
        except Exception as exc:  # noqa: BLE001
            log.debug("drivers: Schlagzeilen %s %s: %s", term, day, exc)
    seen, out = set(), []
    for it in items:
        key = it.headline.lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append({"headline": it.headline, "source": it.source, "url": it.url, "published": it.published,
                    "sentiment": round(it.sentiment, 2)})
        if len(out) >= limit:
            break
    return out


def _pct(x: float | None, d: int = 1) -> str:
    return "–" if x is None else f"{x:+.{d}f}".replace(".", ",") + " %"


def _summary(name: str, dec: dict | None, market_label: str, sector_label: str | None, days: list[dict],
             sent: tuple | None, hi_lo: dict) -> list[str]:
    """Klartext, wichtigstes zuerst."""
    lines: list[str] = []
    if dec and dec.get("own") is not None:
        total, own, mk, sc = dec["total"], dec["own"], dec["market"], dec.get("sector")
        span = "im letzten Monat" if dec["days"] == 21 else "in den letzten drei Monaten" if dec["days"] == 63 else f"in {dec['days']} Handelstagen"
        drivers = [("der Markt", mk, market_label)]
        if sc is not None and sector_label:
            drivers.append(("die Branche", sc, sector_label))
        drivers.append(("Unternehmensspezifisches", own, None))
        parts = [f"{label} ({extra}) {_pct(v)}" if extra else f"{label} {_pct(v)}" for label, v, extra in drivers]
        lines.append(f"{name}: {span} {_pct(total)}. Davon " + ", ".join(parts) + ".")
        names = {"der Markt": f"Markt ({market_label})", "die Branche": f"Branche ({sector_label})",
                 "Unternehmensspezifisches": "das Unternehmen selbst"}
        up = sorted([(names[lb], v) for lb, v, _ in drivers if (v or 0) >= 0.5], key=lambda t: -t[1])
        down = sorted([(names[lb], v) for lb, v, _ in drivers if (v or 0) <= -0.5], key=lambda t: t[1])
        bits = []
        if up:
            bits.append("Rückenwind: " + ", ".join(f"{n} {_pct(v)}" for n, v in up))
        if down:
            bits.append("Gegenwind: " + ", ".join(f"{n} {_pct(v)}" for n, v in down))
        if bits:
            lines.append(". ".join(bits) + ".")
    if days:
        d0 = days[0]
        head = (d0.get("news") or [{}])[0].get("headline")
        lines.append(f"Zuletzt deutlich: {pd.Timestamp(d0['day']):%d.%m.} {_pct(d0['pct'])} (Markt {_pct(d0['market_pct'])})"
                     + (f" – „{head}“." if head else "."))
    if sent and sent[0] is not None and sent[1]:
        mood = "positiv" if sent[0] > 0.15 else "negativ" if sent[0] < -0.15 else "gemischt"
        lines.append(f"Aktuelle Nachrichtenlage: {mood} ({sent[1]} Meldungen).")
    if hi_lo.get("from_high") is not None:
        fh = hi_lo["from_high"]
        if fh < -25:
            lines.append(f"Der Kurs liegt {abs(fh):.0f} % unter dem Jahreshoch – ein tiefer Rücksetzer.")
        elif fh > -3:
            lines.append("Der Kurs notiert nahe am Jahreshoch.")
    return lines


def compute(symbol: str, settings=None) -> dict:
    sym = symbol.upper()
    info = market.cached_info(sym) or {}
    name = info.get("name") or sym
    stock = _closes(sym, "1y")
    if stock is None or len(stock) < 30:
        return {"symbol": sym, "empty": True, "reason": "Zu wenige Tageskurse für eine Erklärung."}
    cc = country_of(sym, info)
    idx_sym, idx_label = INDEX_BY_COUNTRY.get(cc or "", WORLD)
    mkt = _closes(idx_sym, "1y")
    if mkt is None and idx_sym != WORLD[0]:
        idx_sym, idx_label = WORLD
        mkt = _closes(idx_sym, "1y")
    sec_sym = None
    try:
        from . import brain

        sec_sym = brain.sector_of(sym)
    except Exception:  # noqa: BLE001
        pass
    sec = _closes(sec_sym, "1y") if sec_sym else None
    sector_label = SECTOR_NAMES.get(sec_sym, sec_sym) if sec is not None else None
    ccy = "EUR" if gettex.is_gettex(sym) else (info.get("currency") or None)
    mkt = in_currency(mkt, INDEX_CCY.get(idx_sym), ccy)
    sec = in_currency(sec, "USD", ccy)
    fit = _fit(stock, mkt, sec)
    if sec is not None and (fit.get("beta_x") is None or fit["beta_x"] < 0.15):
        # schwingt kaum (oder gegenläufig) mit dem Branchenindex: Branche weglassen statt verwirrender Vorzeichen
        sec, sector_label, sec_sym = None, None, None
        fit = _fit(stock, mkt, None)
    windows = []
    for label, n in WINDOWS:
        dec = decompose(stock, mkt, sec, fit, min(n, len(stock) - 1))
        if dec:
            windows.append({"label": label, **{k: (round(v, 1) if isinstance(v, float) else v) for k, v in dec.items()}})
    days = big_days(stock, mkt)
    term = news.search_name(info.get("name"), sym)
    if days and term:
        with ThreadPoolExecutor(max_workers=min(4, len(days))) as pool:
            for d, heads in zip(days, pool.map(lambda d: headlines_on(term, d["day"]), days), strict=False):
                d["news"] = heads
    sent = news.cached_sentiment(sym)
    last = float(stock.iloc[-1])
    hi, lo = float(stock.max()), float(stock.min())
    hi_lo = {"high": round(hi, 2), "low": round(lo, 2), "from_high": round((last / hi - 1) * 100, 1) if hi else None,
             "from_low": round((last / lo - 1) * 100, 1) if lo else None}
    main_window = next((w for w in windows if w["label"] == "Monat"), windows[0] if windows else None)
    return {
        "symbol": sym, "name": name, "generated_at": int(time.time()), "v": CALC_VERSION,
        "market": {"symbol": idx_sym, "label": idx_label}, "sector": {"symbol": sec_sym, "label": sector_label} if sector_label else None,
        "fit": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in fit.items()},
        "windows": windows, "big_days": days, "range": hi_lo,
        "news": {"sentiment": round(sent[0], 2) if sent and sent[0] is not None else None, "count": sent[1] if sent else 0},
        "summary": _summary(name, main_window, idx_label, sector_label, days, sent, hi_lo),
    }


def _run(sym: str, settings) -> dict:
    try:
        with market.fresh_reads():
            out = compute(sym, settings)
        store = marketstore.get_store()
        if store is not None:
            store.put(f"why:{sym}", out)
        return out
    finally:
        with _LOCK:
            _RUNNING.pop(sym, None)


def get(symbol: str, settings=None, budget: float = 3.0, force: bool = False) -> dict:
    sym = symbol.upper()
    store = marketstore.get_store()
    hit = store.get_with_age(f"why:{sym}") if store is not None and not force else None
    if hit and hit[0].get("v") == CALC_VERSION and hit[1] < TTL:
        return hit[0]
    with _LOCK:
        fut = _RUNNING.get(sym)
        if fut is None:
            fut = _POOL.submit(_run, sym, settings)
            _RUNNING[sym] = fut
    try:
        return fut.result(timeout=max(0.2, budget))
    except FutureTimeout:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("drivers %s: %s", sym, exc)
        return {"symbol": sym, "error": str(exc)}
    if hit and hit[0].get("v") == CALC_VERSION:
        return {**hit[0], "refreshing": True}
    return {"symbol": sym, "pending": True}
