"""Kurse von gettex (Börse München) über die öffentliche onvista-Schnittstelle.

Symbole haben die Form <ISIN>.GTX, z. B. DE0007164600.GTX für SAP auf gettex. So ist jeder Wert eindeutig und
ohne zusätzliche Zuordnungstabelle auflösbar.

Verfügbar: aktueller Kurs mit Geld/Brief (Echtzeit), Tageskurse (OHLCV) über Jahre und die Einzelgeschäfte
(„Times & Sales“) eines Handelstags. Fertige Minutenkerzen gibt onvista nicht frei; der Tagesverlauf wird deshalb
aus den Einzelgeschäften der letzten Handelstage gebaut. Die heutige Tageskerze entsteht aus dem aktuellen Kurs.
"""

from __future__ import annotations

import threading
import time
from datetime import date, timedelta

import pandas as pd
import requests

BASE = "https://api.onvista.de/api/v1"
HEADERS = {"User-Agent": "Mozilla/5.0 (TradeHelper)", "Accept": "application/json"}
SUFFIX = ".GTX"
MARKET = "_TRO"  # gettex in der onvista-Systematik
KINDS = {"STOCK": "stocks", "FUND": "funds"}
SEARCH_TYPES = {"STOCK": "Aktie", "FUND": "ETF/Fonds"}
_SNAP: dict[str, tuple[float, dict]] = {}
_SNAP_TTL = 30
_STALE_MAX = 24 * 3600  # bei Drosselung: letzter Stand bis zu einem Tag

# Schonender Umgang mit onvista: höchstens ~3 Anfragen pro Sekunde, und nach „429 Too many requests“ eine
# Pause für alle Anfragen (1 Minute, bei Wiederholung doppelt so lang bis 15 Minuten) statt weiter anzuklopfen.
_MIN_GAP = 0.35
_LOCK = threading.Lock()
_STATE = {"last": 0.0, "cool_until": 0.0, "cool": 60.0}
_EOD: dict[tuple, tuple[float, pd.DataFrame]] = {}
_EOD_TTL = 600


class GettexError(RuntimeError):
    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


def is_gettex(symbol: str) -> bool:
    return symbol.upper().endswith(SUFFIX)


def isin_of(symbol: str) -> str:
    return symbol.upper()[: -len(SUFFIX)]


def to_symbol(isin: str) -> str:
    return f"{isin.upper()}{SUFFIX}"


def _pause() -> None:
    with _LOCK:
        if time.time() < _STATE["cool_until"]:
            return  # schon in der Pause (mehrere gleichzeitige Fehlschläge zählen einmal)
        _STATE["cool_until"] = time.time() + _STATE["cool"]
        _STATE["cool"] = min(_STATE["cool"] * 2, 900.0)


def throttle_status() -> dict:
    left = _STATE["cool_until"] - time.time()
    return {"paused": left > 0, "seconds_left": max(0, int(left))}


def _get(path: str, params: dict | None = None) -> dict:
    with _LOCK:
        now = time.time()
        if now < _STATE["cool_until"]:
            left = int(_STATE["cool_until"] - now) + 1
            raise GettexError(f"onvista bremst gerade – neuer Versuch in {left // 60} min {left % 60} s"
                              if left >= 60 else f"onvista bremst gerade – neuer Versuch in {left} s", 429)
        slot = max(now, _STATE["last"] + _MIN_GAP)  # eigenen Zeitschlitz reservieren, gewartet wird außerhalb der Sperre
        _STATE["last"] = slot
    if slot > now:
        time.sleep(slot - now)
        if time.time() < _STATE["cool_until"]:  # während des Wartens hat eine andere Anfrage die Pause ausgelöst
            raise GettexError("onvista bremst gerade – TradeHelper pausiert kurz", 429)
    try:
        r = requests.get(BASE + path, params=params, headers=HEADERS, timeout=(5, 10))
    except requests.RequestException as exc:
        # Keine Antwort (Zeitüberschreitung, Verbindung abgelehnt): ebenfalls pausieren – sonst wartet jede Anfrage
        # bis zur Zeitüberschreitung und Seiten wie die Übersicht laden minutenlang
        _pause()
        raise GettexError(f"onvista antwortet nicht ({type(exc).__name__}) – TradeHelper pausiert kurz", 503) from exc
    if r.status_code == 429:
        _pause()
        raise GettexError("onvista bremst gerade (zu viele Anfragen) – TradeHelper pausiert kurz", 429)
    if r.ok:
        _STATE["cool"] = 60.0
    if r.status_code == 404:
        raise GettexError("Wert bei onvista nicht gefunden", 404)
    if not r.ok:
        raise GettexError(f"onvista meldet Fehler {r.status_code}", r.status_code)
    try:
        return r.json()
    except ValueError as exc:
        raise GettexError("Unerwartete Antwort von onvista") from exc


def snapshot(isin: str) -> dict:
    isin = isin.upper()
    cached = _SNAP.get(isin)
    if cached and time.time() - cached[0] < _SNAP_TTL:
        return cached[1]
    # Seit November 2026 bremst onvista den alten Pfad /stocks/…/snapshot für alle mit „429 Too many requests“.
    # Der gleichwertige Pfad über /instruments/{Typ}/… liefert denselben Snapshot – der alte bleibt nur als Rückfall.
    # (Den alten Pfad nicht mehr probieren: jedes 429 dort würde die Pause für alle Werte auslösen.)
    paths = [f"/instruments/STOCK/ISIN:{isin}/snapshot", f"/instruments/FUND/ISIN:{isin}/snapshot"]
    errors: list[GettexError] = []
    for path in paths:
        try:
            snap = _get(path)
        except GettexError as exc:
            errors.append(exc)
            if exc.status == 429:
                break  # gebremst: nicht noch den nächsten Pfad anfragen
            continue
        if snap.get("instrument"):
            _SNAP[isin] = (time.time(), snap)
            return snap
    # Nur gebremst oder gestört (nicht „gibt es nicht“)? Dann lieber den letzten bekannten Stand der letzten Stunden
    if cached and any(e.status != 404 for e in errors) and time.time() - cached[0] < _STALE_MAX:
        return cached[1]
    real = next((e for e in errors if e.status not in (404, None)), None) or (errors[-1] if errors else None)
    if real is not None and real.status != 404:
        raise GettexError(f"{isin}: {real}", real.status)
    raise GettexError(f"{isin}: kein Wert gefunden ({real})", 404)


def gettex_quote(snap: dict) -> dict:
    for q in (snap.get("quoteList") or {}).get("list", []):
        if (q.get("market") or {}).get("codeMarket") == MARKET:
            return q
    name = (snap.get("instrument") or {}).get("name", "Der Wert")
    raise GettexError(f"{name} wird auf gettex nicht gehandelt. Bitte eine andere Börse wählen.")


def _ts(value) -> int | None:
    if not value:
        return None
    try:
        return int(pd.Timestamp(value).timestamp())
    except (ValueError, TypeError):
        return None


def info(symbol: str) -> dict:
    snap = snapshot(isin_of(symbol))
    q = gettex_quote(snap)
    inst = snap["instrument"]
    return {
        "symbol": symbol.upper(), "name": inst.get("name"), "ticker": inst.get("symbol"), "isin": inst.get("isin"),
        "exchange": "gettex", "currency": q.get("isoCurrency") or "EUR",
        "type": SEARCH_TYPES.get(inst.get("entityType"), inst.get("entityType")),
        "delay_min": 0 if q.get("codeQualityPrice", "RLT") == "RLT" else 15,
        "quote_source": "gettex über onvista",
        "as_of": _ts(q.get("datetimeLast")),
    }


def quote(symbol: str) -> dict:
    q = gettex_quote(snapshot(isin_of(symbol)))
    return {"price": q.get("last"), "previous_close": q.get("previousLast"), "open": q.get("open"),
            "high": q.get("high"), "low": q.get("low"), "volume": q.get("totalVolume"), "time": _ts(q.get("datetimeLast")),
            "realtime": q.get("codeQualityPrice") == "RLT", "bid": q.get("bid"), "ask": q.get("ask"),
            "bid_time": _ts(q.get("datetimeBid"))}


def _range_for(period: str) -> tuple[str, date]:
    days = {"1mo": 31, "3mo": 92, "6mo": 183, "1y": 366, "2y": 731, "5y": 1827, "10y": 3653, "max": 3653}.get(period, 366)
    return ("Y1" if days <= 366 else "Y5" if days <= 1827 else "Y10"), date.today() - timedelta(days=days)


INTRADAY_RULES = {"1s": "1s", "1m": "1min", "3m": "3min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "2h": "2h"}
INTRADAY_DAYS = {"1d": 1, "5d": 5}
_TAS: dict[tuple[str, str], tuple[float, tuple[list, list, list]]] = {}
_TAS_TTL = 15


def _trades(symbol: str, day: date | None) -> tuple[list, list, list]:
    """Einzelgeschäfte eines Handelstags (ohne day: heute). Vergangene Tage bleiben im Speicher."""
    key = (symbol.upper(), day.isoformat() if day else "heute")
    hit = _TAS.get(key)
    if hit and (day is not None or time.time() - hit[0] < _TAS_TTL):
        return hit[1]
    snap = snapshot(isin_of(symbol))
    q = gettex_quote(snap)
    inst = snap["instrument"]
    params = {"idNotation": q["market"]["idNotation"]}
    if day:
        params["startDate"] = day.isoformat()
    data = _get(f"/instruments/{inst['entityType']}/{inst['entityValue']}/times_and_sales", params)
    out = (data.get("datetimePrice") or [], data.get("price") or [], data.get("volume") or [])
    if len(_TAS) > 2000:
        _TAS.clear()
    _TAS[key] = (time.time(), out)
    return out


def intraday(symbol: str, period: str = "1d", interval: str = "5m") -> pd.DataFrame:
    """Minutenkerzen der letzten 1 oder 5 Handelstage aus den Einzelgeschäften."""
    days = INTRADAY_DAYS.get(period)
    rule = INTRADAY_RULES.get(interval)
    if not days or not rule:
        raise GettexError("Für gettex gibt es Minutenkerzen nur für den letzten Tag oder die letzten 5 Handelstage.")
    berlin_today = pd.Timestamp.now(tz="Europe/Berlin").date()
    frames, found = [], 0
    for back in range(0, 12):
        if found >= days:
            break
        d = berlin_today - timedelta(days=back)
        if d.weekday() >= 5:
            continue
        times, prices, vols = _trades(symbol, None if back == 0 else d)
        if not times:
            continue
        idx = pd.to_datetime(times, unit="s", utc=True).tz_convert("Europe/Berlin")
        f = pd.DataFrame({"price": prices, "volume": vols}, index=idx).astype(float)
        f = f[f.index.date == d]
        if f.empty:
            continue
        frames.append(f)
        found += 1
    if not frames:
        raise GettexError("Für diesen Wert gab es in den letzten Tagen keine Geschäfte auf gettex.")
    t = pd.concat(frames).sort_index()
    ohlc = t["price"].resample(rule).ohlc()
    ohlc["volume"] = t["volume"].resample(rule).sum()
    return ohlc.dropna(subset=["close"])


RANGE_DAYS = {"Y1": 366, "Y5": 1827, "Y10": 3653}


def range_start(rng: str) -> date:
    return date.today() - timedelta(days=RANGE_DAYS.get(rng, 366))


def history(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    if interval in INTRADAY_RULES:
        return intraday(symbol, period, interval)
    if interval not in ("1d", "1wk"):
        raise GettexError("Unbekanntes Intervall.")
    snap = snapshot(isin_of(symbol))
    q = gettex_quote(snap)
    inst = snap["instrument"]
    rng, start = _range_for(period)
    key = (symbol.upper(), rng)
    cached = _EOD.get(key)
    if cached and time.time() - cached[0] < _EOD_TTL:
        df = cached[1].copy()
    else:
        # Immer den ganzen Bereich laden: Der Zwischenspeicher gilt pro Bereich (Y1/Y5/Y10), nicht pro Zeitraum.
        # Sonst bekäme nach einer 1-Monats-Abfrage auch die 1-Jahres-Abfrage nur einen Monat.
        data = _get(f"/instruments/{inst['entityType']}/{inst['entityValue']}/eod_history",
                    {"idNotation": q["market"]["idNotation"], "range": rng, "startDate": range_start(rng).isoformat()})
        if rng == "Y10" and not data.get("datetimeLast"):
            data = _get(f"/instruments/{inst['entityType']}/{inst['entityValue']}/eod_history",
                        {"idNotation": q["market"]["idNotation"], "range": "Y5",
                         "startDate": (date.today() - timedelta(days=1827)).isoformat()})
        times = data.get("datetimeLast") or []
        if not times:
            raise GettexError("Keine Kursdaten von gettex")
        idx = pd.to_datetime(times, unit="s", utc=True).tz_convert("Europe/Berlin").normalize()
        df = pd.DataFrame({"open": data.get("first"), "high": data.get("high"), "low": data.get("low"),
                           "close": data.get("last"), "volume": data.get("volume") or [0.0] * len(times)}, index=idx)
        df = df[~df.index.duplicated(keep="last")].astype(float)
        _EOD[key] = (time.time(), df.copy())
    df = _with_today(df, q)
    df = df[df.index >= pd.Timestamp(start, tz="Europe/Berlin")]
    if interval == "1wk":
        df = df.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        df = df.dropna(subset=["close"])
    return df


def _with_today(df: pd.DataFrame, q: dict) -> pd.DataFrame:
    """Heutige Kerze aus dem aktuellen Kurs ergänzen bzw. aktualisieren."""
    t = _ts(q.get("datetimeLast"))
    last = q.get("last")
    if not t or last is None:
        return df
    day = pd.Timestamp(t, unit="s", tz="UTC").tz_convert("Europe/Berlin").normalize()
    row = {"open": q.get("open") or last, "high": max(q.get("high") or last, last), "low": min(q.get("low") or last, last),
           "close": last, "volume": float(q.get("totalVolume") or 0)}  # "volume" ist nur das letzte Einzelgeschäft
    out = df.copy()
    if len(out) and day < out.index[-1]:
        return out
    out.loc[day] = row
    return out.sort_index()


def search(query: str, limit: int = 8) -> list[dict]:
    """Aktien und ETFs; ob ein Wert auf gettex gehandelt wird, zeigt sich erst beim Hinzufügen."""
    data = _get("/instruments/query", {"searchValue": query, "limit": limit * 2})
    out = []
    for x in data.get("list", []):
        if x.get("entityType") not in SEARCH_TYPES or not x.get("isin"):
            continue
        out.append({"symbol": to_symbol(x["isin"]), "name": x.get("name"), "ticker": x.get("symbol"),
                    "isin": x["isin"], "exchange": "gettex", "type": SEARCH_TYPES[x["entityType"]],
                    "currency": "EUR", "default": True})
        if len(out) >= limit:
            break
    return out
