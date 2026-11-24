"""Kursdaten über yfinance (kein API-Key nötig).

Symbole folgen der Yahoo-Notation. Die Endung legt den Börsenplatz fest und damit die Handelswährung:
AAPL (Nasdaq, USD), APC.DE (Xetra, EUR), APC.F (Frankfurt, EUR), SAP.DE, ^GDAXI (Index), BTC-EUR, EURUSD=X.

Für die Anzeige lassen sich Kurse in eine andere Währung umrechnen (Tageskurs des jeweiligen Handelstags).
"""

from __future__ import annotations

import contextvars
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd
import requests

from . import gettex, marketstore

log = logging.getLogger(__name__)

_CACHE: dict[tuple, tuple[float, pd.DataFrame]] = {}
_CACHE_TTL = 30  # Sekunden (Yahoo)
_INFO: dict[str, dict] = {}

# Anzeigewährungen, in die umgerechnet werden kann
CURRENCIES = ["EUR", "USD", "CHF", "GBP"]

# Yahoo notiert manche Börsen in der Untereinheit (Pence, Cent)
MINOR_UNITS = {"GBp": ("GBP", 0.01), "GBX": ("GBP", 0.01), "ZAc": ("ZAR", 0.01), "ILA": ("ILS", 0.01)}

# Endung → (Börsenplatz, Währung), falls Yahoo keine Metadaten liefert
SUFFIXES = {
    "GTX": ("gettex", "EUR"), "DE": ("Xetra", "EUR"), "F": ("Frankfurt", "EUR"), "SG": ("Stuttgart", "EUR"), "MU": ("München", "EUR"),
    "BE": ("Berlin", "EUR"), "DU": ("Düsseldorf", "EUR"), "HM": ("Hamburg", "EUR"), "HA": ("Hannover", "EUR"),
    "VI": ("Wien", "EUR"), "PA": ("Euronext Paris", "EUR"), "AS": ("Euronext Amsterdam", "EUR"),
    "BR": ("Euronext Brüssel", "EUR"), "LS": ("Euronext Lissabon", "EUR"), "MI": ("Borsa Italiana", "EUR"),
    "MC": ("Madrid", "EUR"), "HE": ("Helsinki", "EUR"), "IR": ("Dublin", "EUR"), "SW": ("SIX Swiss", "CHF"),
    "L": ("London", "GBp"), "ST": ("Stockholm", "SEK"), "CO": ("Kopenhagen", "DKK"), "OL": ("Oslo", "NOK"),
    "TO": ("Toronto", "CAD"), "V": ("TSX Venture", "CAD"), "AX": ("ASX", "AUD"), "HK": ("Hongkong", "HKD"),
    "T": ("Tokio", "JPY"), "KS": ("Korea", "KRW"), "SS": ("Shanghai", "CNY"), "SZ": ("Shenzhen", "CNY"),
    "NS": ("NSE Indien", "INR"), "BO": ("BSE Indien", "INR"), "SA": ("B3 São Paulo", "BRL"),
    "MX": ("Mexiko", "MXN"), "WA": ("Warschau", "PLN"), "PR": ("Prag", "CZK"),
}
# Verzögerung in Minuten laut Yahoo (help.yahoo.com/kb/SLN2310.html), falls Yahoo sie nicht selbst mitliefert
DELAYS = {"DE": 15, "F": 15, "SG": 15, "MU": 15, "BE": 15, "DU": 15, "HM": 15, "HA": 15, "PA": 15, "AS": 15,
          "BR": 15, "LS": 15, "MI": 15, "MC": 15, "VI": 15, "L": 20, "SW": 30}
_META: dict[str, dict] = {}  # letzter Kurszeitpunkt je Symbol

SEARCH_TYPES = {"EQUITY", "ETF", "INDEX", "CRYPTOCURRENCY", "CURRENCY", "MUTUALFUND", "FUTURE"}
LONG_PERIODS = {"2y", "5y", "10y", "max"}


class MarketDataError(RuntimeError):
    pass


@dataclass
class Quote:
    symbol: str
    price: float
    previous_close: float | None
    change: float | None
    change_pct: float | None
    currency: str | None
    name: str | None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _yf():
    import yfinance as yf  # lazy import, damit Tests ohne Netzwerk laufen

    return yf


# ---------- Börsenplatz und Währung ----------

def guess_listing(symbol: str) -> tuple[str | None, str | None]:
    """Börsenplatz und Währung aus der Schreibweise ableiten (Fallback ohne Netzwerk)."""
    s = symbol.upper()
    if s.endswith("=X"):
        pair = s[:-2]
        return "Devisen", pair[3:6] if len(pair) >= 6 else "USD"
    if s.startswith("^"):
        return "Index", None
    if "-" in s and "." not in s:
        quote = s.rsplit("-", 1)[1]
        if len(quote) == 3 and quote.isalpha():
            return "Krypto", quote
    if "." in s:
        return SUFFIXES.get(s.rsplit(".", 1)[1], (None, None))
    return "USA", "USD"


def base_currency(ccy: str | None) -> tuple[str | None, float]:
    """GBp → (GBP, 0.01); alles andere unverändert."""
    if not ccy:
        return None, 1.0
    return MINOR_UNITS.get(ccy, (ccy, 1.0))


def symbol_info(symbol: str) -> dict:
    """Name, Börsenplatz und Handelswährung eines Symbols. Wirft MarketDataError, wenn es keine Kurse gibt."""
    s = symbol.upper()
    if s in _INFO:
        return _INFO[s]
    store = marketstore.get_store()
    if store is not None:
        saved = store.get(f"info:{s}", max_age=INFO_TTL)
        if saved:
            _INFO[s] = saved
            return saved
    info = _fetch_info(s)
    _INFO[s] = info
    if store is not None:
        store.put(f"info:{s}", info)
    return info


def cached_info(symbol: str) -> dict | None:
    """Stammdaten nur aus dem Speicher (ohne Netzwerk); fehlt etwas, wird es im Hintergrund geholt."""
    s = symbol.upper()
    if s in _INFO:
        return _INFO[s]
    store = marketstore.get_store()
    saved = store.get(f"info:{s}") if store is not None else None
    if saved:
        _INFO[s] = saved
        return saved
    key = "i:" + s
    with _INFLIGHT_LOCK:
        if key in _INFLIGHT:
            return None
        _INFLIGHT.add(key)

    def run():
        try:
            symbol_info(s)
        except Exception:  # noqa: BLE001
            pass
        finally:
            with _INFLIGHT_LOCK:
                _INFLIGHT.discard(key)

    _BG.submit(run)
    return None


def _fetch_info(s: str) -> dict:
    if gettex.is_gettex(s):
        try:
            return gettex.info(s)
        except gettex.GettexError as exc:
            raise MarketDataError(str(exc)) from exc
    exchange, currency = guess_listing(s)
    info = {"symbol": s, "name": None, "exchange": exchange, "currency": currency, "type": None}
    try:
        t = _yf().Ticker(s)
        df = t.history(period="5d", interval="1d", auto_adjust=True)
    except Exception as exc:  # noqa: BLE001
        raise MarketDataError(f"Kursabruf für {s} fehlgeschlagen: {exc}") from exc
    if df is None or df.empty:
        raise MarketDataError(f"Keine Kursdaten für {s}. Symbol über die Suche auswählen.")
    md = {}
    try:
        md = getattr(t, "history_metadata", None) or t.get_history_metadata() or {}
    except Exception:  # noqa: BLE001 – Metadaten sind optional
        md = {}
    info.update({
        "name": md.get("longName") or md.get("shortName") or info["name"],
        "exchange": md.get("fullExchangeName") or md.get("exchangeName") or info["exchange"],
        "currency": md.get("currency") or info["currency"],
        "type": md.get("instrumentType"),
    })
    if info["type"] == "INDEX":
        info["currency"] = None  # Indexpunkte, keine Währung
    info["delay_min"], info["quote_source"] = _delay(t, s)
    return info


def _delay(ticker, symbol: str) -> tuple[int | None, str | None]:
    """Kursverzögerung in Minuten (0 = Echtzeit) und Quelle, bevorzugt direkt von Yahoo."""
    try:
        inf = ticker.info or {}
        delay = inf.get("exchangeDataDelayedBy")
        source = inf.get("quoteSourceName")
        if source and "real time" in source.lower():
            return 0, source  # Yahoo meldet bei Nasdaq-Werten teils 15 Min., liefert aber Echtzeit
        if delay is not None:
            return int(delay), source
    except Exception:  # noqa: BLE001 – info ist optional und manchmal langsam oder gesperrt
        pass
    s = symbol.upper()
    if s.endswith("=X") or ("-" in s and "." not in s and len(s.rsplit("-", 1)[1]) == 3):
        return 0, None
    if "." in s:
        return DELAYS.get(s.rsplit(".", 1)[1]), None
    return None, None


def last_trade_time(symbol: str) -> int | None:
    """Zeitpunkt des letzten Kurses (Unix-Sekunden) aus dem letzten Abruf."""
    return _META.get(symbol.upper(), {}).get("market_time")


def search(query: str, limit: int = 15) -> list[dict]:
    """Suche nach Name, Symbol oder ISIN. Zuerst gettex (Standardbörse), danach alle Börsen, die Yahoo kennt."""
    q = query.strip()
    if not q:
        return []
    first: list[dict] = []
    try:
        first = gettex.search(q, limit=6)
    except gettex.GettexError as exc:
        log.info("gettex-Suche nicht möglich: %s", exc)
    try:
        rest = _search_yahoo(q, limit)
    except MarketDataError:
        if first:
            return first
        raise
    return first + rest


def _search_yahoo(q: str, limit: int) -> list[dict]:
    quotes: list[dict] = []
    try:
        quotes = _yf().Search(q, max_results=limit, news_count=0).quotes
    except Exception:  # noqa: BLE001 – ältere yfinance-Versionen: direkt bei Yahoo fragen
        try:
            r = requests.get(
                "https://query2.finance.yahoo.com/v1/finance/search",
                params={"q": q, "quotesCount": limit, "newsCount": 0},
                headers={"User-Agent": "Mozilla/5.0 TradeHelper"}, timeout=10,
            )
            r.raise_for_status()
            quotes = r.json().get("quotes", [])
        except (requests.RequestException, ValueError) as exc:
            raise MarketDataError(f"Suche fehlgeschlagen: {exc}") from exc
    out = []
    for x in quotes:
        sym = x.get("symbol")
        if not sym or x.get("quoteType") not in SEARCH_TYPES:
            continue
        exchange, currency = guess_listing(sym)
        out.append({
            "symbol": sym.upper(),
            "name": x.get("longname") or x.get("shortname") or sym,
            "exchange": x.get("exchDisp") or exchange or x.get("exchange"),
            "type": x.get("typeDisp") or x.get("quoteType"),
            "currency": None if x.get("quoteType") == "INDEX" else currency,
        })
    return out


# ---------- Kurse ----------

def _raw_history(symbol: str, period: str, interval: str) -> pd.DataFrame:
    if interval in ("1d", "1wk"):
        df = _daily_history(symbol, period)
        if interval == "1wk":
            df = df.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last",
                                           "volume": "sum"}).dropna(subset=["close"])
        return df.copy()
    key = (symbol.upper(), period, interval)
    cached = _CACHE.get(key)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1].copy()
    if gettex.is_gettex(symbol):
        try:
            df = gettex.history(symbol, period, interval)
            q = gettex.quote(symbol)
        except gettex.GettexError as exc:
            raise MarketDataError(str(exc)) from exc
        if q.get("time"):
            _META[symbol.upper()] = {"market_time": q["time"]}
        return df.copy()
    if interval == "1s":
        raise MarketDataError("Sekundenkerzen gibt es nur für Werte an gettex.")
    fetch, rule = _YF_RESAMPLE.get(interval, (interval, None))
    df = _yahoo_history(symbol, period=period, interval=fetch)
    if rule:
        df = df.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["close"])
    _CACHE[key] = (time.time(), df)
    return df.copy()


def _yahoo_history(symbol: str, period: str | None = None, interval: str = "1d", start: str | None = None) -> pd.DataFrame:
    try:
        t = _yf().Ticker(symbol)
        if start:
            df = t.history(start=start, interval=interval, auto_adjust=True)
        else:
            df = t.history(period=period, interval=interval, auto_adjust=True)
    except Exception as exc:  # noqa: BLE001
        raise MarketDataError(f"Kursabruf für {symbol} fehlgeschlagen: {exc}") from exc
    if df is None or df.empty:
        raise MarketDataError(f"Keine Kursdaten für {symbol} (Symbol prüfen, Yahoo-Notation).")
    try:
        md = getattr(t, "history_metadata", None) or {}
        if md.get("regularMarketTime"):
            _META[symbol.upper()] = {"market_time": int(md["regularMarketTime"])}
    except Exception:  # noqa: BLE001
        pass
    return df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])


# ---------- Tageskerzen aus dem dauerhaften Speicher ----------
#
# Ablauf pro Abfrage:
# 1. Reicht die gespeicherte Tiefe (span_days) für den Zeitraum? Nein → einmalig mindestens 5 Jahre holen.
# 2. Ist der Stand älter als DAILY_TTL? In Hintergrund-Jobs (fresh_reads) wird sofort nachgeladen; bei Abfragen aus
#    der Oberfläche wird der gespeicherte Stand geliefert und im Hintergrund aktualisiert (stale-while-revalidate).
# 3. Die heutige Kerze wird mit dem letzten bekannten Kurs (Quote-Speicher) aktualisiert. So sind Übersicht und
#    Analyse live, ohne die Historie neu zu laden.

PERIOD_DAYS = {"1d": 4, "5d": 8, "1mo": 32, "3mo": 93, "6mo": 184, "1y": 367, "2y": 732, "5y": 1828, "10y": 3654,
               "max": 3654, "ytd": 367}
FIRST_SPAN = 1828            # beim ersten Abruf 5 Jahre, danach reicht jeder Zeitraum bis 5 Jahre aus dem Speicher
DAILY_TTL = 20 * 60          # Tageskerzen höchstens alle 20 Minuten nachladen (der heutige Kurs kommt aus den Quotes)
DAILY_TTL_IDLE = 6 * 3600    # am Wochenende
STALE_MAX = 4 * 86400        # älter als das: auch in der Oberfläche warten, statt veraltete Kurse zu zeigen
QUOTE_TTL = 45               # Sekunden
QUOTE_STALE = 15 * 60
INFO_TTL = 7 * 86400

_FRESH = contextvars.ContextVar("th_fresh_reads", default=False)
_BG = ThreadPoolExecutor(max_workers=3, thread_name_prefix="kurse")
_INFLIGHT: set[str] = set()
_INFLIGHT_LOCK = threading.Lock()
_SYMBOL_LOCKS: dict[str, threading.Lock] = {}


@contextmanager
def fresh_reads():
    """In diesem Block wird bei veralteten Daten synchron nachgeladen (für Bericht, Alarme, Schattendepot)."""
    token = _FRESH.set(True)
    try:
        yield
    finally:
        _FRESH.reset(token)


def ensure_fresh(symbols: list[str], max_age: float | None = None, quotes: bool = True, workers: int = 4) -> None:
    """Vor Hintergrund-Jobs (Bericht, Alarme, Schattendepot): veraltete Kerzen und Kurse dieser Werte synchron
    nachladen. Danach lesen die Jobs alles aus dem Speicher – auch aus eigenen Threads."""
    store = marketstore.get_store()
    if store is None or not symbols:
        return
    limit = _ttl() if max_age is None else max_age

    def one(sym: str) -> None:
        try:
            # Nur auffrischen, was schon im Speicher liegt; Unbekanntes holt der normale Abruf ohnehin frisch
            meta = store.series(sym)
            if meta and time.time() - float(meta["fetched_at"]) > limit:
                refresh_daily(sym)
            if quotes:
                hit = store.quote(sym)
                if hit and time.time() - hit[1] > QUOTE_TTL:
                    fetch_live(sym)
        except Exception as exc:  # noqa: BLE001
            log.info("Aktualisieren von %s vor dem Job fehlgeschlagen: %s", sym, exc)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(symbols))), thread_name_prefix="frisch") as pool:
        list(pool.map(one, list(dict.fromkeys(s.upper() for s in symbols))))


def _lock_for(symbol: str) -> threading.Lock:
    with _INFLIGHT_LOCK:
        return _SYMBOL_LOCKS.setdefault(symbol.upper(), threading.Lock())


def _weekend() -> bool:
    return date.today().weekday() >= 5


def _ttl() -> float:
    return DAILY_TTL_IDLE if _weekend() else DAILY_TTL


def _fetch_daily(symbol: str, days: int | None = None, start: str | None = None) -> pd.DataFrame:
    """Tageskerzen direkt von der Quelle: entweder die letzten `days` Tage oder ab `start`."""
    if gettex.is_gettex(symbol):
        period = "10y" if (days or 0) > 1828 else "5y" if (days or 0) > 366 else "1y"
        try:
            df = gettex.history(symbol, period, "1d")
            q = gettex.quote(symbol)
        except gettex.GettexError as exc:
            raise MarketDataError(str(exc)) from exc
        if q.get("time"):
            _META[symbol.upper()] = {"market_time": q["time"]}
        if start:
            df = df[_days(df.index) >= pd.Timestamp(start)]
        return df
    if start:
        return _yahoo_history(symbol, start=start)
    period = "10y" if (days or 0) > 1828 else "5y" if (days or 0) > 731 else "2y" if (days or 0) > 366 else "1y"
    return _yahoo_history(symbol, period=period)


def refresh_daily(symbol: str, full: bool = False) -> int:
    """Gespeicherte Tageskerzen auf den neuesten Stand bringen. Gibt die Zahl geschriebener Kerzen zurück."""
    store = marketstore.get_store()
    sym = symbol.upper()
    if store is None:
        return 0
    with _lock_for(sym):
        meta = store.series(sym)
        if full or not meta or not meta.get("last_day"):
            span = max(FIRST_SPAN, int(meta["span_days"]) if meta else 0)
            df = _fetch_daily(sym, days=span)
            return store.put_daily(sym, df, span_days=span, source="gettex" if gettex.is_gettex(sym) else "yahoo")
        if time.time() - meta["fetched_at"] < 30:
            return 0  # gerade erst geholt (gleichzeitige Anfragen)
        start = (pd.Timestamp(meta["last_day"]) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        df = _fetch_daily(sym, start=start)
        if df.empty:
            store.touch(sym)
            return 0
        old = store.daily(sym, start=start)
        if _adjusted(old, df):
            # Dividende/Split: die Quelle hat ältere Kurse rückwirkend angepasst → alles neu holen
            span = int(meta["span_days"])
            full_df = _fetch_daily(sym, days=span)
            return store.put_daily(sym, full_df, span_days=span, replace_from="0000-00-00")
        return store.put_daily(sym, df, replace_from=start)


def _adjusted(old: pd.DataFrame, new: pd.DataFrame) -> bool:
    """Weichen sich die Schlusskurse gemeinsamer, abgeschlossener Tage deutlich ab?"""
    if old.empty or new.empty:
        return False
    a = old["close"].copy()
    b = new["close"].copy()
    a.index = _days(a.index)
    b.index = _days(b.index)
    common = a.index.intersection(b.index)
    common = common[common < pd.Timestamp(date.today())]
    if len(common) == 0:
        return False
    diff = (a.loc[common] / b.loc[common] - 1).abs()
    return bool((diff > 0.005).any())


def _schedule_refresh(symbol: str) -> None:
    sym = symbol.upper()
    with _INFLIGHT_LOCK:
        if sym in _INFLIGHT:
            return
        _INFLIGHT.add(sym)

    def run():
        try:
            refresh_daily(sym)
        except Exception as exc:  # noqa: BLE001
            log.info("Nachladen %s im Hintergrund fehlgeschlagen: %s", sym, exc)
        finally:
            with _INFLIGHT_LOCK:
                _INFLIGHT.discard(sym)

    _BG.submit(run)


def _daily_history(symbol: str, period: str) -> pd.DataFrame:
    store = marketstore.get_store()
    sym = symbol.upper()
    need = PERIOD_DAYS.get(period, 367)
    if store is None:  # ohne Speicher (z. B. einzelne Tests): wie früher direkt holen, kurz im Arbeitsspeicher
        key = (sym, period, "1d")
        cached = _CACHE.get(key)
        if cached and time.time() - cached[0] < _CACHE_TTL:
            return cached[1].copy()
        df = _fetch_daily(sym, days=need)
        cut = pd.Timestamp(date.today() - timedelta(days=need))
        df = df[_days(df.index) >= cut]
        _CACHE[key] = (time.time(), df)
        return df.copy()
    meta = store.series(sym)
    if not meta or int(meta["span_days"]) < need:
        span = max(need, FIRST_SPAN)
        with _lock_for(sym):
            meta = store.series(sym)
            if not meta or int(meta["span_days"]) < need:
                store.put_daily(sym, _fetch_daily(sym, days=span), span_days=span,
                                source="gettex" if gettex.is_gettex(sym) else "yahoo")
    else:
        age = time.time() - float(meta["fetched_at"])
        if age > _ttl():
            if _FRESH.get() or age > STALE_MAX:
                try:
                    refresh_daily(sym)
                except MarketDataError as exc:
                    log.info("Nachladen %s fehlgeschlagen, nutze gespeicherten Stand: %s", sym, exc)
            else:
                _schedule_refresh(sym)
    start = (date.today() - timedelta(days=need)).isoformat()
    df = _overlay_quote(sym, store.daily(sym, start=start))
    if df.empty:
        raise MarketDataError(f"Keine Kursdaten für {sym}.")
    if sym not in _META:
        q = store.quote(sym)
        if q and q[0].get("time"):
            _META[sym] = {"market_time": int(q[0]["time"])}
    return df


def _quote_day(t: int | None) -> pd.Timestamp | None:
    if not t:
        return None
    return pd.Timestamp(int(t), unit="s", tz="UTC").tz_convert("Europe/Berlin").tz_localize(None).normalize()


def _overlay_quote(symbol: str, df: pd.DataFrame) -> pd.DataFrame:
    """Heutige Kerze mit dem neuesten gespeicherten Kurs aktualisieren (oder anhängen)."""
    store = marketstore.get_store()
    if store is None or df.empty:
        return df
    hit = store.quote(symbol)
    if not hit:
        return df
    q, fetched = hit
    price, day = q.get("price"), _quote_day(q.get("time"))
    if price is None or day is None or time.time() - fetched > 6 * 3600:
        return df
    last = df.index[-1]
    if day < last:
        return df
    out = df.copy()
    if day == last:
        out.loc[last, "close"] = price
        out.loc[last, "high"] = max(float(out.loc[last, "high"]), price)
        out.loc[last, "low"] = min(float(out.loc[last, "low"]), price)
    elif day.weekday() < 5:
        o = q.get("open") or price
        row = pd.DataFrame({"open": [o], "high": [max(q.get("high") or price, price)],
                            "low": [min(q.get("low") or price, price)], "close": [price],
                            "volume": [float(q.get("volume") or 0)]}, index=pd.DatetimeIndex([day]))
        out = pd.concat([out, row])
    return out


def _days(idx) -> pd.DatetimeIndex:
    """Kalendertage in Ortszeit der Börse (ohne Zeitzonenverschiebung über Mitternacht)."""
    idx = pd.DatetimeIndex(idx)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def fx_rates(frm: str, to: str, period: str = "1y") -> pd.Series:
    """Tagesschlusskurse 1 frm = x to."""
    try:
        df = _raw_history(f"{frm}{to}=X", period if period in LONG_PERIODS else "1y", "1d")
    except MarketDataError as exc:
        raise MarketDataError(f"Wechselkurs {frm}→{to} nicht verfügbar") from exc
    s = df["close"].copy()
    s.index = _days(s.index)
    return s[~s.index.duplicated(keep="last")]


def convert_history(df: pd.DataFrame, native: str | None, target: str | None, period: str = "1y",
                    rates: pd.Series | None = None) -> pd.DataFrame:
    """Rechnet Open/High/Low/Close mit dem Tageskurs des jeweiligen Handelstags um. Volumen bleibt gleich."""
    if not native or not target:
        return df
    base, factor = base_currency(native)
    if base == target and factor == 1:
        return df
    out = df.copy()
    mult = factor
    if base != target:
        if rates is None:
            rates = fx_rates(base, target, period)
        days = _days(out.index)
        aligned = rates.reindex(rates.index.union(days)).sort_index().ffill().bfill().reindex(days)
        mult = aligned.to_numpy() * factor
    for col in ("open", "high", "low", "close"):
        out[col] = out[col].to_numpy() * mult
    return out


INTRADAY = {"1s", "1m", "3m", "5m", "15m", "30m", "1h", "2h"}
# Yahoo kennt kein 3m und 2h: aus 1m bzw. 1h zusammengefasst. Sekundenkerzen gibt es nur bei gettex.
_YF_RESAMPLE = {"3m": ("1m", "3min"), "2h": ("1h", "2h")}


def supports_intraday(symbol: str) -> bool:
    return True  # gettex: letzte 5 Handelstage aus den Einzelgeschäften


def intraday_limit(symbol: str) -> str | None:
    """Längster Zeitraum mit Minutenkerzen (None = wie bei Yahoo üblich)."""
    return "5d" if gettex.is_gettex(symbol) else None


def get_history(symbol: str, period: str = "1y", interval: str = "1d", currency: str | None = None) -> pd.DataFrame:
    """OHLCV-Daten (Spalten open, high, low, close, volume). Mit currency in diese Währung umgerechnet,
    sofern das Symbol eine Währung hat (Indizes bleiben in Punkten)."""
    df = _raw_history(symbol, period, interval)
    if currency:
        native = symbol_info(symbol).get("currency")
        df = convert_history(df, native, currency, period)
    return df


def convert_price(value: float | None, frm: str | None, to: str | None, day=None) -> float | None:
    """Einzelnen Kurs umrechnen, mit dem Wechselkurs des Tages `day` (sonst dem letzten)."""
    if value is None or not frm or not to:
        return value
    base, factor = base_currency(frm)
    value = value * factor
    if base == to:
        return value
    rates = fx_rates(base, to, "5y")
    if day is None:
        return value * float(rates.iloc[-1])
    ts = pd.Timestamp(day).normalize()
    prior = rates[rates.index <= ts]
    rate = prior.iloc[-1] if len(prior) else rates.iloc[0]
    return value * float(rate)


def shown_currency(native: str | None, target: str | None) -> str | None:
    """Welche Währung nach get_history(currency=target) tatsächlich angezeigt wird."""
    if not native:
        return None
    return target or native


def fetch_live(symbol: str) -> dict:
    """Aktuellen Kurs direkt bei der Quelle holen (Handelswährung), gettex mit Geld/Brief, Yahoo aus der Minutenkerze.
    Wird vom Hintergrunddienst laufend aufgerufen; das Ergebnis landet im Quote-Speicher."""
    symbol = symbol.upper()
    out: dict = {"symbol": symbol}
    if gettex.is_gettex(symbol):
        try:
            q, inf = gettex.quote(symbol), gettex.info(symbol)
        except gettex.GettexError as exc:
            raise MarketDataError(str(exc)) from exc
        out.update(price=q["price"], previous_close=q.get("previous_close"), time=q.get("time"), bid=q.get("bid"),
                   ask=q.get("ask"), bid_time=q.get("bid_time"), delay_min=inf.get("delay_min"),
                   open=q.get("open"), high=q.get("high"), low=q.get("low"), volume=q.get("volume"),
                   native=inf.get("currency"))
        if q.get("time"):
            _META[symbol] = {"market_time": q["time"]}
    else:
        df = _raw_history(symbol, "5d", "1d")
        price, prev = float(df["close"].iloc[-1]), (float(df["close"].iloc[-2]) if len(df) > 1 else None)
        t = last_trade_time(symbol)
        day_high = day_low = day_open = None
        try:
            m = _raw_history(symbol, "1d", "1m")
            if len(m) and pd.Timestamp(m.index[-1]).date() == pd.Timestamp(df.index[-1]).date():
                price = float(m["close"].iloc[-1])
                t = int(pd.Timestamp(m.index[-1]).timestamp()) + 60  # Ende der letzten Minutenkerze
                day_high, day_low, day_open = float(m["high"].max()), float(m["low"].min()), float(m["open"].iloc[0])
        except MarketDataError:
            pass
        info = {}
        try:
            info = symbol_info(symbol)
        except MarketDataError:
            pass
        out.update(price=price, previous_close=prev, time=min(t, int(time.time())) if t else None, bid=None, ask=None,
                   bid_time=None, delay_min=info.get("delay_min"), open=day_open, high=day_high, low=day_low,
                   native=info.get("currency"))
    store = marketstore.get_store()
    if store is not None and out.get("price") is not None:
        store.put_quote(symbol, out)
    return out


def _schedule_quote(symbol: str) -> None:
    key = "q:" + symbol.upper()
    with _INFLIGHT_LOCK:
        if key in _INFLIGHT:
            return
        _INFLIGHT.add(key)

    def run():
        try:
            fetch_live(symbol)
        except Exception as exc:  # noqa: BLE001
            log.info("Kurs %s im Hintergrund nicht abrufbar: %s", symbol, exc)
        finally:
            with _INFLIGHT_LOCK:
                _INFLIGHT.discard(key)

    _BG.submit(run)


def native_live(symbol: str) -> dict:
    """Aktueller Kurs in Handelswährung – aus dem Speicher, wenn frisch genug, sonst von der Quelle."""
    symbol = symbol.upper()
    store = marketstore.get_store()
    hit = store.quote(symbol) if store is not None else None
    if hit:
        data, fetched = hit
        age = time.time() - fetched
        if age < QUOTE_TTL:
            return dict(data)
        if age < QUOTE_STALE and not _FRESH.get():
            _schedule_quote(symbol)
            return {**data, "stale": True}
    return fetch_live(symbol)


def quote_times(symbols: list[str]) -> dict[str, dict]:
    """Zeitpunkt des letzten Kurses je Wert aus dem Speicher (ohne Netz): {"time", "delay_min", "fetched_at"}."""
    store = marketstore.get_store()
    if store is None or not symbols:
        return {}
    out = {}
    for sym, (data, fetched) in store.quotes(list({s for s in symbols if s})).items():
        out[sym] = {"time": data.get("time"), "delay_min": data.get("delay_min"), "fetched_at": int(fetched)}
    return out


def live(symbol: str, currency: str | None = None) -> dict:
    """Schneller, möglichst aktueller Kurs für die Anzeige, optional umgerechnet."""
    raw = native_live(symbol)
    native = raw.get("native")
    out = {k: raw.get(k) for k in ("symbol", "price", "previous_close", "time", "bid", "ask", "bid_time", "delay_min")}
    if currency and native:
        for k in ("price", "previous_close", "bid", "ask"):
            out[k] = convert_price(out[k], native, currency) if out.get(k) is not None else None
    out["currency"] = shown_currency(native, currency)
    p, prev = out.get("price"), out.get("previous_close")
    out["change_pct"] = round((p / prev - 1) * 100, 3) if p and prev else None
    for k in ("price", "previous_close", "bid", "ask"):
        if out.get(k) is not None:
            out[k] = round(float(out[k]), 4)
    if raw.get("stale"):
        out["stale"] = True
    return out


def get_quote(symbol: str) -> Quote:
    symbol = symbol.upper()
    raw = native_live(symbol)
    info: dict = {}
    try:
        info = symbol_info(symbol)
    except MarketDataError:
        pass
    price, prev = raw.get("price"), raw.get("previous_close")
    if price is None:
        raise MarketDataError(f"Kein Kurs für {symbol}")
    change = price - prev if prev else None
    change_pct = change / prev * 100 if prev else None
    return Quote(symbol, round(float(price), 4), prev, change, change_pct, info.get("currency") or raw.get("native"),
                 info.get("name"))
