"""Ausbruch- und Rutsch-Wahrscheinlichkeit (Breakout / Breakdown) aus der eigenen Kursgeschichte eines Werts.

Frage: Schließt der Kurs in den nächsten N Handelstagen über dem Hoch (Ausbruch) bzw. unter dem Tief (Rutsch) der
letzten Wochen?

Statt fester Regeln schauen wir, wie es in der Vergangenheit *dieses* Werts ausging, wenn die Lage ähnlich war
(k nächste Nachbarn): Abstand zu Hoch und Tief in Tagesschwankungen (ATR), RSI, Steigung des 20-Tage-Schnitts,
Enge der Bollinger-Bänder (Ruhe vor dem Sturm) und Schwung der letzten 5 Tage. Die Trefferquote der ähnlichsten Tage
wird zur Basisquote hin gezogen, damit wenige Beispiele nicht zu extremen Werten führen.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind

# Wie weit nach vorn geschaut wird und welches Hoch/Tief zählt – je Anlagehorizont
SETUP = {"short": (5, 10), "medium": (10, 20), "long": (20, 55)}
MIN_SAMPLES = 120
SHRINK = 12  # Gewicht der Basisquote (in „Beispielen“)


def _features(d: pd.DataFrame, look: int) -> pd.DataFrame:
    close, high, low = d["close"], d["high"], d["low"]
    atr = d["atr"] if "atr" in d else ind.atr(d)
    rsi = d["rsi"] if "rsi" in d else ind.rsi(close)
    sma20 = d["sma20"] if "sma20" in d else ind.sma(close, 20)
    hi = high.rolling(look).max()
    lo = low.rolling(look).min()
    if "bb_upper" in d and "bb_lower" in d:
        bw = (d["bb_upper"] - d["bb_lower"]) / close
    else:
        sd = close.rolling(20).std()
        bw = 4 * sd / close
    atr_pct = atr / close * 100
    return pd.DataFrame({
        "d_hi": (hi - close) / atr,
        "d_lo": (close - lo) / atr,
        "rsi": rsi / 10,
        "slope": (sma20 / sma20.shift(5) - 1) * 100 / atr_pct,
        "squeeze": bw.rolling(120, min_periods=40).rank(pct=True) * 2,
        "mom5": (close / close.shift(5) - 1) * 100 / atr_pct,
    }), hi, lo


def probabilities(d: pd.DataFrame, horizon: str = "medium") -> dict | None:
    """Wahrscheinlichkeiten für Ausbruch nach oben/unten innerhalb des Horizonts (0..1) oder None (zu wenig Daten)."""
    ahead, look = SETUP.get(horizon, SETUP["medium"])
    if len(d) < MIN_SAMPLES + ahead + look:
        return None
    feats, hi, lo = _features(d, look)
    close = d["close"].to_numpy(dtype=float)
    n = len(d)
    # fut_max[t] = höchster Schluss in t+1 .. t+ahead (NaN, solange die Zukunft noch nicht bekannt ist)
    win = np.lib.stride_tricks.sliding_window_view(close[1:], ahead)
    fut_max = np.full(n, np.nan)
    fut_min = np.full(n, np.nan)
    fut_max[: len(win)] = win.max(axis=1)
    fut_min[: len(win)] = win.min(axis=1)
    with np.errstate(invalid="ignore"):
        up = fut_max > hi.to_numpy()
        down = fut_min < lo.to_numpy()

    X = feats.to_numpy(dtype=float)
    valid = ~np.isnan(X).any(axis=1)
    train = valid.copy()
    train[n - ahead:] = False  # Zukunft noch nicht bekannt
    train &= ~np.isnan(fut_max) & ~np.isnan(fut_min)
    if train.sum() < MIN_SAMPLES or not valid[-1]:
        return None
    Xt, yu, yd = X[train], up[train].astype(float), down[train].astype(float)
    mu, sd = Xt.mean(axis=0), Xt.std(axis=0)
    sd[sd == 0] = 1
    Z = (Xt - mu) / sd
    z = (X[-1] - mu) / sd
    dist = np.sqrt(((Z - z) ** 2).sum(axis=1))
    k = int(min(max(30, len(Z) // 6), 120))
    idx = np.argsort(dist)[:k]
    base_u, base_d = float(yu.mean()), float(yd.mean())
    p_u = (yu[idx].sum() + SHRINK * base_u) / (k + SHRINK)
    p_d = (yd[idx].sum() + SHRINK * base_d) / (k + SHRINK)
    hi_now, lo_now = float(hi.iloc[-1]), float(lo.iloc[-1])
    return {
        "days": ahead,
        "up": round(float(p_u), 3), "down": round(float(p_d), 3),
        "base_up": round(base_u, 3), "base_down": round(base_d, 3),
        "level_up": round(hi_now, 4), "level_down": round(lo_now, 4),
        "samples": int(train.sum()), "neighbors": k,
        "tilt": tilt(p_u, p_d, base_u, base_d),
        "edge": round(edge(p_u, p_d, base_u, base_d), 3),
    }


def edge(p_up: float, p_down: float, base_up: float, base_down: float) -> float:
    """Richtung als Zahl (−1 … +1): zu zwei Dritteln der direkte Vergleich oben/unten, zu einem Drittel die
    Abweichung vom Üblichen. So zählt bei einem Wert, der sonst fast immer neue Hochs macht, auch ein deutlich
    erhöhtes Rutsch-Risiko – und ein Dauer-Abwärtstrend bleibt trotzdem ein Risiko."""
    return float((2 * (p_up - p_down) + ((p_up - base_up) - (p_down - base_down))) / 3)


def tilt(p_up: float, p_down: float, base_up: float | None = None, base_down: float | None = None) -> str:
    """Grobe Richtung: „up“, „down“ oder „neutral“."""
    e = edge(p_up, p_down, base_up if base_up is not None else p_up, base_down if base_down is not None else p_down)
    if e <= -0.1 and p_down >= 0.25:
        return "down"
    if e >= 0.1 and p_up >= 0.3:
        return "up"
    return "neutral"


def describe(bo: dict, fmt=lambda v: f"{v:.2f}") -> str:
    wk = "Woche" if bo["days"] <= 5 else f"{bo['days'] // 5} Wochen"
    return (f"Ausbruch über {fmt(bo['level_up'])}: {bo['up'] * 100:.0f} % · Rutsch unter {fmt(bo['level_down'])}: "
            f"{bo['down'] * 100:.0f} % (nächste {wk})")
