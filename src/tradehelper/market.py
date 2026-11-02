"""Kursdaten über yfinance (kein API-Key nötig).

Symbole folgen der Yahoo-Notation, z. B. AAPL, SAP.DE, ^GDAXI, BTC-USD, EURUSD=X.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pandas as pd

_CACHE: dict[tuple, tuple[float, pd.DataFrame]] = {}
_CACHE_TTL = 60  # Sekunden


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


def get_history(symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
    """OHLCV-Daten mit Spalten open, high, low, close, volume (Index: Zeitstempel)."""
    key = (symbol.upper(), period, interval)
    cached = _CACHE.get(key)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1].copy()

    try:
        df = _yf().Ticker(symbol).history(period=period, interval=interval, auto_adjust=True)
    except Exception as exc:  # noqa: BLE001
        raise MarketDataError(f"Kursabruf für {symbol} fehlgeschlagen: {exc}") from exc
    if df is None or df.empty:
        raise MarketDataError(f"Keine Kursdaten für {symbol} (Symbol prüfen, Yahoo-Notation).")

    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
    _CACHE[key] = (time.time(), df)
    return df.copy()


def get_quote(symbol: str) -> Quote:
    symbol = symbol.upper()
    df = get_history(symbol, period="5d", interval="1d")
    price = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2]) if len(df) > 1 else None

    currency = name = None
    try:
        fi = _yf().Ticker(symbol).fast_info
        currency = fi.get("currency") if hasattr(fi, "get") else getattr(fi, "currency", None)
        last = fi.get("last_price") if hasattr(fi, "get") else getattr(fi, "last_price", None)
        if last:
            price = float(last)
    except Exception:  # noqa: BLE001 – Zusatzinfos sind optional
        pass

    change = price - prev if prev else None
    change_pct = change / prev * 100 if prev else None
    return Quote(symbol, round(price, 4), prev, change, change_pct, currency, name)
