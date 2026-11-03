"""Kursdaten über yfinance (kein API-Key nötig).

Symbole folgen der Yahoo-Notation. Die Endung legt den Börsenplatz fest und damit die Handelswährung:
AAPL (Nasdaq, USD), APC.DE (Xetra, EUR), APC.F (Frankfurt, EUR), SAP.DE, ^GDAXI (Index), BTC-EUR, EURUSD=X.

Für die Anzeige lassen sich Kurse in eine andere Währung umrechnen (Tageskurs des jeweiligen Handelstags).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import pandas as pd
import requests

log = logging.getLogger(__name__)

_CACHE: dict[tuple, tuple[float, pd.DataFrame]] = {}
_CACHE_TTL = 60  # Sekunden
_INFO: dict[str, dict] = {}

# Anzeigewährungen, in die umgerechnet werden kann
CURRENCIES = ["EUR", "USD", "CHF", "GBP"]

# Yahoo notiert manche Börsen in der Untereinheit (Pence, Cent)
MINOR_UNITS = {"GBp": ("GBP", 0.01), "GBX": ("GBP", 0.01), "ZAc": ("ZAR", 0.01), "ILA": ("ILS", 0.01)}

# Endung → (Börsenplatz, Währung), falls Yahoo keine Metadaten liefert
SUFFIXES = {
    "DE": ("Xetra", "EUR"), "F": ("Frankfurt", "EUR"), "SG": ("Stuttgart", "EUR"), "MU": ("München", "EUR"),
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
    _INFO[s] = info
    return info


def _delay(ticker, symbol: str) -> tuple[int | None, str | None]:
    """Kursverzögerung in Minuten (0 = Echtzeit) und Quelle, bevorzugt direkt von Yahoo."""
    try:
        inf = ticker.info or {}
        delay = inf.get("exchangeDataDelayedBy")
        if delay is not None:
            return int(delay), inf.get("quoteSourceName")
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
    """Suche nach Name, Symbol oder ISIN. Liefert alle Börsenplätze, die Yahoo kennt."""
    q = query.strip()
    if not q:
        return []
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
    key = (symbol.upper(), period, interval)
    cached = _CACHE.get(key)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1].copy()
    try:
        t = _yf().Ticker(symbol)
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
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    _CACHE[key] = (time.time(), df)
    return df.copy()


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


def get_quote(symbol: str) -> Quote:
    symbol = symbol.upper()
    df = _raw_history(symbol, "5d", "1d")
    price = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2]) if len(df) > 1 else None
    info = {}
    try:
        info = symbol_info(symbol)
    except MarketDataError:
        pass
    change = price - prev if prev else None
    change_pct = change / prev * 100 if prev else None
    return Quote(symbol, round(price, 4), prev, change, change_pct, info.get("currency"), info.get("name"))
