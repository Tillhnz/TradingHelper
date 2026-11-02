"""Chartanalyse: Indikator-Snapshot, Einzelsignale und regelbasierter Gesamtscore."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from . import indicators as ind


@dataclass
class Signal:
    name: str
    score: int  # -2 .. +2
    text: str


@dataclass
class Analysis:
    symbol: str
    last_close: float
    change_pct_1d: float | None
    metrics: dict
    signals: list[Signal] = field(default_factory=list)
    support: float | None = None
    resistance: float | None = None

    @property
    def score(self) -> int:
        return sum(s.score for s in self.signals)

    @property
    def max_score(self) -> int:
        return 2 * len(self.signals) or 1

    @property
    def normalized(self) -> float:
        """Score auf -1..+1 normiert."""
        return round(self.score / self.max_score, 3)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "last_close": self.last_close,
            "change_pct_1d": self.change_pct_1d,
            "score": self.score,
            "normalized_score": self.normalized,
            "support": self.support,
            "resistance": self.resistance,
            "metrics": self.metrics,
            "signals": [s.__dict__ for s in self.signals],
        }


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else round(v, 4)


def support_resistance(df: pd.DataFrame, lookback: int = 60) -> tuple[float | None, float | None]:
    """Einfache Unterstützung/Widerstand: Swing-Tiefs/-Hochs der letzten `lookback` Kerzen."""
    tail = df.tail(lookback)
    if len(tail) < 10:
        return None, None
    close = tail["close"].iloc[-1]
    lows = tail["low"][(tail["low"] == tail["low"].rolling(5, center=True).min())]
    highs = tail["high"][(tail["high"] == tail["high"].rolling(5, center=True).max())]
    below = lows[lows < close]
    above = highs[highs > close]
    sup = _f(below.max()) if not below.empty else _f(tail["low"].min())
    res = _f(above.min()) if not above.empty else _f(tail["high"].max())
    return sup, res


def analyze(symbol: str, df: pd.DataFrame) -> Analysis:
    if len(df) < 30:
        raise ValueError(f"Zu wenige Kerzen für {symbol} ({len(df)}), mindestens 30 nötig.")
    d = ind.add_all(df)
    last = d.iloc[-1]
    close = float(last["close"])
    prev = float(d["close"].iloc[-2])

    metrics = {k: _f(last[k]) for k in [
        "sma20", "sma50", "sma200", "ema9", "ema21", "rsi", "macd", "signal", "hist",
        "bb_upper", "bb_mid", "bb_lower", "bb_pctb", "stoch_k", "stoch_d", "adx", "plus_di",
        "minus_di", "atr", "volume", "vol_sma20",
    ]}
    metrics["atr_pct"] = _f(last["atr"] / close * 100) if metrics["atr"] else None
    metrics["perf_1m"] = _f((close / d["close"].iloc[-22] - 1) * 100) if len(d) > 22 else None
    metrics["perf_3m"] = _f((close / d["close"].iloc[-64] - 1) * 100) if len(d) > 64 else None

    a = Analysis(symbol.upper(), round(close, 4), _f((close / prev - 1) * 100), metrics)
    a.support, a.resistance = support_resistance(d)
    sig = a.signals

    # Trend (Kurs vs. gleitende Durchschnitte)
    s50, s200 = metrics["sma50"], metrics["sma200"]
    if s200:
        if close > s200 and (s50 or 0) > s200:
            sig.append(Signal("Trend", 2, "Kurs und SMA50 über SMA200 – intakter Aufwärtstrend"))
        elif close < s200 and s50 and s50 < s200:
            sig.append(Signal("Trend", -2, "Kurs und SMA50 unter SMA200 – Abwärtstrend"))
        else:
            sig.append(Signal("Trend", 0, "Gemischtes Trendbild um die SMA200"))
    elif s50:
        sig.append(Signal("Trend", 1 if close > s50 else -1,
                          f"Kurs {'über' if close > s50 else 'unter'} SMA50 (SMA200 noch nicht verfügbar)"))

    if ind.crossed_above(d["sma50"], d["sma200"]):
        sig.append(Signal("Golden Cross", 2, "SMA50 hat SMA200 nach oben gekreuzt"))
    elif ind.crossed_below(d["sma50"], d["sma200"]):
        sig.append(Signal("Death Cross", -2, "SMA50 hat SMA200 nach unten gekreuzt"))

    # Momentum: RSI
    r = metrics["rsi"]
    if r is not None:
        if r < 30:
            sig.append(Signal("RSI", 1, f"RSI {r:.0f} – überverkauft, Rebound möglich"))
        elif r > 70:
            sig.append(Signal("RSI", -1, f"RSI {r:.0f} – überkauft, Rücksetzer möglich"))
        elif r >= 50:
            sig.append(Signal("RSI", 1, f"RSI {r:.0f} – positives Momentum"))
        else:
            sig.append(Signal("RSI", -1, f"RSI {r:.0f} – schwaches Momentum"))

    # MACD
    if ind.crossed_above(d["macd"], d["signal"]):
        sig.append(Signal("MACD", 2, "MACD kreuzt Signallinie nach oben (Kaufsignal)"))
    elif ind.crossed_below(d["macd"], d["signal"]):
        sig.append(Signal("MACD", -2, "MACD kreuzt Signallinie nach unten (Verkaufssignal)"))
    elif metrics["hist"] is not None:
        rising = d["hist"].iloc[-1] > d["hist"].iloc[-2]
        if metrics["hist"] > 0:
            sig.append(Signal("MACD", 1, "MACD über Signallinie" + (", Histogramm steigt" if rising else "")))
        else:
            sig.append(Signal("MACD", -1, "MACD unter Signallinie" + (", Histogramm fällt" if not rising else "")))

    # Bollinger
    pb = metrics["bb_pctb"]
    if pb is not None:
        if pb < 0:
            sig.append(Signal("Bollinger", 1, "Kurs unter dem unteren Band – Übertreibung nach unten"))
        elif pb > 1:
            sig.append(Signal("Bollinger", -1, "Kurs über dem oberen Band – Übertreibung nach oben"))

    # Stochastik
    k, dd = metrics["stoch_k"], metrics["stoch_d"]
    if k is not None and dd is not None:
        if k < 20 and ind.crossed_above(d["stoch_k"], d["stoch_d"]):
            sig.append(Signal("Stochastik", 1, "Stochastik dreht im überverkauften Bereich nach oben"))
        elif k > 80 and ind.crossed_below(d["stoch_k"], d["stoch_d"]):
            sig.append(Signal("Stochastik", -1, "Stochastik dreht im überkauften Bereich nach unten"))

    # Trendstärke (ADX) – verstärkt nur die Richtung
    ad = metrics["adx"]
    if ad is not None and ad > 25 and metrics["plus_di"] is not None:
        bull = metrics["plus_di"] > metrics["minus_di"]
        sig.append(Signal("ADX", 1 if bull else -1,
                          f"ADX {ad:.0f} – starker {'Aufwärts' if bull else 'Abwärts'}trend"))

    # Volumen-Bestätigung
    if metrics["vol_sma20"] and metrics["volume"] and metrics["volume"] > 1.5 * metrics["vol_sma20"]:
        up = close > prev
        sig.append(Signal("Volumen", 1 if up else -1,
                          f"Volumen {metrics['volume'] / metrics['vol_sma20']:.1f}× über Schnitt bei "
                          f"{'steigendem' if up else 'fallendem'} Kurs"))
    return a


@dataclass
class Recommendation:
    symbol: str
    action: str  # "Kaufen prüfen" | "Halten / beobachten" | "Reduzieren prüfen"
    emoji: str
    combined: float
    technical: float
    sentiment: float | None
    reasons: list[str]


def recommend(a: Analysis, sentiment: float | None, news_weight: float = 0.3) -> Recommendation:
    """Kombiniert technischen Score (70 %) und News-Sentiment (30 %) zu einer Einschätzung."""
    tech = a.normalized
    combined = tech if sentiment is None else (1 - news_weight) * tech + news_weight * sentiment
    combined = round(combined, 3)
    if combined >= 0.35:
        action, emoji = "Kaufen prüfen", "🟢"
    elif combined <= -0.35:
        action, emoji = "Reduzieren prüfen", "🔴"
    else:
        action, emoji = "Halten / beobachten", "🟡"

    top = sorted(a.signals, key=lambda s: abs(s.score), reverse=True)[:3]
    reasons = [s.text for s in top]
    if sentiment is not None:
        mood = "positiv" if sentiment > 0.15 else "negativ" if sentiment < -0.15 else "neutral"
        reasons.append(f"News-Stimmung {mood} ({sentiment:+.2f})")
    return Recommendation(a.symbol, action, emoji, combined, tech, sentiment, reasons)
