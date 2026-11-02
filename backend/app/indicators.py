"""Technische Indikatoren (reines pandas, keine TA-Lib nötig).

Alle Funktionen erwarten Series/DataFrames mit den Spalten open, high, low, close, volume.
Formeln entsprechen den Standarddefinitionen (RSI/ATR mit Wilder-Glättung wie bei TradingView).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder's Moving Average wie ta.rma in Pine Script: Start mit SMA der ersten n Werte,
    danach rekursiv rma = (rma_prev * (n-1) + x) / n."""
    vals = s.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    valid = np.flatnonzero(~np.isnan(vals))
    if len(valid) < n:
        return pd.Series(out, index=s.index)
    start = valid[0]
    seed_end = start + n - 1
    if np.isnan(vals[start:seed_end + 1]).any():
        return s.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out[seed_end] = vals[start:seed_end + 1].mean()
    for i in range(seed_end + 1, len(vals)):
        x = vals[i]
        out[i] = out[i - 1] if np.isnan(x) else (out[i - 1] * (n - 1) + x) / n
    return pd.Series(out, index=s.index)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = rma(delta.clip(lower=0), n)
    loss = rma(-delta.clip(upper=0), n)
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    out = out.where(loss != 0, 100.0)  # nur Gewinne -> RSI 100
    return out.where(gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * sd, mid - k * sd
    return pd.DataFrame({
        "bb_mid": mid, "bb_upper": upper, "bb_lower": lower,
        "bb_pctb": (close - lower) / (upper - lower), "bb_width": (upper - lower) / mid,
    })


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift()
    return pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return rma(true_range(df), n)


def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3, smooth: int = 3) -> pd.DataFrame:
    ll = df["low"].rolling(k, min_periods=k).min()
    hh = df["high"].rolling(k, min_periods=k).max()
    raw = 100 * (df["close"] - ll) / (hh - ll).replace(0, np.nan)
    kline = raw.rolling(smooth, min_periods=smooth).mean()
    return pd.DataFrame({"stoch_k": kline, "stoch_d": kline.rolling(d, min_periods=d).mean()})


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


def adx(df: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    tr = rma(true_range(df), n)
    plus_di = 100 * rma(plus_dm, n) / tr
    minus_di = 100 * rma(minus_dm, n) / tr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return pd.DataFrame({"plus_di": plus_di, "minus_di": minus_di, "adx": rma(dx, n)})


def add_all(df: pd.DataFrame) -> pd.DataFrame:
    """Hängt alle Standard-Indikatoren als Spalten an (Kopie)."""
    out = df.copy()
    c = out["close"]
    out["sma20"], out["sma50"], out["sma200"] = sma(c, 20), sma(c, 50), sma(c, 200)
    out["ema9"], out["ema21"] = ema(c, 9), ema(c, 21)
    out["rsi"] = rsi(c)
    out = out.join(macd(c)).join(bollinger(c)).join(stochastic(out)).join(adx(out))
    out["atr"] = atr(out)
    out["obv"] = obv(out)
    out["vol_sma20"] = sma(out["volume"], 20)
    return out


def crossed_above(a: pd.Series, b: pd.Series | float) -> bool:
    """True, wenn a auf der letzten Kerze b von unten nach oben gekreuzt hat (wie ta.crossover)."""
    b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
    if len(a) < 2 or pd.isna(a.iloc[-2:]).any() or pd.isna(b.iloc[-2:]).any():
        return False
    return bool(a.iloc[-2] <= b.iloc[-2] and a.iloc[-1] > b.iloc[-1])


def crossed_below(a: pd.Series, b: pd.Series | float) -> bool:
    b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
    if len(a) < 2 or pd.isna(a.iloc[-2:]).any() or pd.isna(b.iloc[-2:]).any():
        return False
    return bool(a.iloc[-2] >= b.iloc[-2] and a.iloc[-1] < b.iloc[-1])
