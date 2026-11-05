"""Chartanalyse und Empfehlung, abgestimmt auf die Anlagestrategie (Horizont und Risikobereitschaft).

Ablauf:
1. analyze()   berechnet Indikatoren und Einzelsignale (−2 … +2). Der Horizont gewichtet sie: kurzfristig zählen
               Momentum-Signale (RSI, MACD, Stochastik, EMA 9/21), langfristig Trend und 6-/12-Monats-Momentum.
2. recommend() mischt Technik und News (News-Anteil je Horizont), zieht bei hoher Schwankung je nach Risiko ab
               und vergleicht mit den Schwellen des Risikoprofils. Konservativ kauft nie unter der 200-Tage-Linie
               und verlangt ein besseres Chance/Risiko-Verhältnis. Dazu gibt es Stopp, Ziel und optional eine
               Positionsgröße (Risiko pro Position in Prozent des Depots).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators as ind

# ---------- Anlagestrategie ----------

HORIZONS: dict[str, dict] = {
    "short": {
        "label": "Kurzfristig",
        "weights": {"Trend": 0.5, "Golden Cross": 0.5, "Death Cross": 0.5, "RSI": 1.5, "MACD": 1.5, "Bollinger": 1.5,
                    "Stochastik": 1.5, "ADX": 1.0, "Volumen": 1.5, "EMA 9/21": 1.5, "Momentum": 0, "Rücksetzer": 0},
        "news": 0.40, "stop_atr": 1.5, "sr_lookback": 40, "period": "1y", "crv_gate": True,
    },
    "medium": {
        "label": "Mittelfristig",
        "weights": {"EMA 9/21": 0.5, "Momentum": 0.75, "Rücksetzer": 0.5},
        "news": 0.30, "stop_atr": 2.5, "sr_lookback": 60, "period": "1y", "crv_gate": True,
    },
    "long": {
        "label": "Langfristig",
        "weights": {"Trend": 2.0, "Golden Cross": 1.5, "Death Cross": 1.5, "RSI": 0.5, "MACD": 0.5, "Bollinger": 0,
                    "Stochastik": 0, "ADX": 0.5, "Volumen": 0, "EMA 9/21": 0, "Momentum": 1.5, "Rücksetzer": 1.0},
        "news": 0.15, "stop_atr": 3.5, "sr_lookback": 250, "period": "2y", "crv_gate": False,
    },
}

RISKS: dict[str, dict] = {
    "conservative": {"label": "Konservativ", "buy": 0.45, "sell": -0.25, "trend_filter": "strict",
                     "vol_limit": 4.0, "vol_penalty": 0.15, "min_crv": 2.0, "risk_per_trade": 0.5, "max_position": 5},
    "balanced": {"label": "Ausgewogen", "buy": 0.35, "sell": -0.35, "trend_filter": "soft",
                 "vol_limit": 6.0, "vol_penalty": 0.10, "min_crv": 1.5, "risk_per_trade": 1.0, "max_position": 10},
    "aggressive": {"label": "Offensiv", "buy": 0.25, "sell": -0.45, "trend_filter": None,
                   "vol_limit": None, "vol_penalty": 0.0, "min_crv": 1.0, "risk_per_trade": 2.0, "max_position": 20},
}


@dataclass(frozen=True)
class Profile:
    horizon: str = "medium"
    risk: str = "balanced"
    portfolio_size: float = 0.0  # 0 = keine Positionsgröße berechnen

    @property
    def h(self) -> dict:
        return HORIZONS.get(self.horizon, HORIZONS["medium"])

    @property
    def r(self) -> dict:
        return RISKS.get(self.risk, RISKS["balanced"])

    @property
    def label(self) -> str:
        return f"{self.h['label']} · {self.r['label']}"

    @property
    def period(self) -> str:
        return self.h["period"]


def profile_from(settings) -> Profile:
    return Profile(getattr(settings, "invest_horizon", "medium"), getattr(settings, "risk_profile", "balanced"),
                   float(getattr(settings, "portfolio_size", 0) or 0))


# ---------- Analyse ----------

@dataclass
class Signal:
    name: str
    score: int  # -2 .. +2
    text: str
    weight: float = 1.0


@dataclass
class Analysis:
    symbol: str
    last_close: float
    change_pct_1d: float | None
    metrics: dict
    signals: list[Signal] = field(default_factory=list)
    support: float | None = None
    resistance: float | None = None
    profile: Profile = field(default_factory=Profile)

    @property
    def score(self) -> float:
        return round(sum(s.score * s.weight for s in self.signals), 2)

    @property
    def max_score(self) -> float:
        return 2 * sum(s.weight for s in self.signals) or 1

    @property
    def normalized(self) -> float:
        """Gewichteter Score auf -1..+1 normiert."""
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
            "profile": {"horizon": self.profile.horizon, "risk": self.profile.risk, "label": self.profile.label},
        }


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else round(v, 4)


def _swing(x: np.ndarray, fn) -> np.ndarray:
    """Werte, die das Minimum/Maximum ihres 5er-Fensters (zentriert) sind – wie rolling(5, center=True)."""
    out = np.zeros(len(x), dtype=bool)
    if len(x) >= 5:
        w = fn(np.lib.stride_tricks.sliding_window_view(x, 5), axis=1)
        out[2:-2] = x[2:-2] == w
    return out


def support_resistance(df: pd.DataFrame, lookback: int = 60) -> tuple[float | None, float | None]:
    """Einfache Unterstützung/Widerstand: Swing-Tiefs/-Hochs der letzten `lookback` Kerzen."""
    tail = df.tail(lookback)
    if len(tail) < 10:
        return None, None
    lo, hi = tail["low"].to_numpy(dtype=float), tail["high"].to_numpy(dtype=float)
    close = float(tail["close"].iloc[-1])
    lows, highs = lo[_swing(lo, np.min)], hi[_swing(hi, np.max)]
    below, above = lows[lows < close], highs[highs > close]
    sup = _f(below.max()) if below.size else _f(np.nanmin(lo))
    res = _f(above.min()) if above.size else _f(np.nanmax(hi))
    return sup, res


def _perf(close: pd.Series, bars: int) -> float | None:
    return _f((close.iloc[-1] / close.iloc[-bars - 1] - 1) * 100) if len(close) > bars else None


def analyze(symbol: str, df: pd.DataFrame, profile: Profile | None = None) -> Analysis:
    p = profile or Profile()
    if len(df) < 30:
        raise ValueError(f"Noch zu wenig Kursverlauf für eine Einschätzung ({len(df)} Kerzen, mindestens 30 nötig).")
    d = df if "rsi" in df.columns else ind.add_all(df)  # Rückblick rechnet die Indikatoren einmal vorab
    last = d.iloc[-1]
    close = float(last["close"])
    prev = float(d["close"].iloc[-2])

    metrics = {k: _f(last[k]) for k in [
        "sma20", "sma50", "sma200", "ema9", "ema21", "rsi", "macd", "signal", "hist",
        "bb_upper", "bb_mid", "bb_lower", "bb_pctb", "stoch_k", "stoch_d", "adx", "plus_di",
        "minus_di", "atr", "volume", "vol_sma20",
    ]}
    metrics["atr_pct"] = _f(last["atr"] / close * 100) if metrics["atr"] else None
    metrics["perf_1m"] = _perf(d["close"], 21)
    metrics["perf_3m"] = _perf(d["close"], 63)
    metrics["perf_6m"] = _perf(d["close"], 126)
    metrics["perf_12m"] = _perf(d["close"], 252)
    high_52w = d["high"].tail(252).max()
    metrics["from_high_pct"] = _f((close / high_52w - 1) * 100) if high_52w else None
    metrics["high_52w"] = _f(high_52w)

    a = Analysis(symbol.upper(), round(close, 4), _f((close / prev - 1) * 100), metrics, profile=p)
    a.support, a.resistance = support_resistance(d, p.h["sr_lookback"])
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

    # Kurzfristiger Trend: EMA 9/21
    if metrics["ema9"] is not None and metrics["ema21"] is not None:
        if ind.crossed_above(d["ema9"], d["ema21"]):
            sig.append(Signal("EMA 9/21", 2, "EMA 9 kreuzt EMA 21 nach oben (kurzfristiges Kaufsignal)"))
        elif ind.crossed_below(d["ema9"], d["ema21"]):
            sig.append(Signal("EMA 9/21", -2, "EMA 9 kreuzt EMA 21 nach unten (kurzfristiges Verkaufssignal)"))
        elif metrics["ema9"] > metrics["ema21"]:
            sig.append(Signal("EMA 9/21", 1, "EMA 9 über EMA 21 – kurzfristig aufwärts"))
        else:
            sig.append(Signal("EMA 9/21", -1, "EMA 9 unter EMA 21 – kurzfristig abwärts"))

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

    # Trendstärke (ADX)
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

    # Mittel- bis langfristiges Momentum (6 und 12 Monate)
    p6, p12 = metrics["perf_6m"], metrics["perf_12m"]
    ref, span = (p12, "12") if p12 is not None else (p6, "6")
    if ref is not None:
        if ref > 10 and (p6 is None or p6 > 0):
            sig.append(Signal("Momentum", 2, f"Starkes {span}-Monats-Momentum ({ref:+.0f} %)"))
        elif ref > 0:
            sig.append(Signal("Momentum", 1, f"Positives {span}-Monats-Momentum ({ref:+.0f} %)"))
        elif ref < -10:
            sig.append(Signal("Momentum", -2, f"Deutlich negatives {span}-Monats-Momentum ({ref:+.0f} %)"))
        else:
            sig.append(Signal("Momentum", -1, f"Schwaches {span}-Monats-Momentum ({ref:+.0f} %)"))

    # Rücksetzer im Aufwärtstrend = Nachkaufchance; tiefer Fall bei gebrochenem Trend = Warnung
    fh = metrics["from_high_pct"]
    if fh is not None and s200:
        if close > s200 and -25 <= fh <= -8:
            sig.append(Signal("Rücksetzer", 1, f"{abs(fh):.0f} % unter dem 52-Wochen-Hoch bei intaktem Trend – Nachkaufchance"))
        elif close < s200 and fh < -30:
            sig.append(Signal("Rücksetzer", -1, f"{abs(fh):.0f} % unter dem 52-Wochen-Hoch, Trend gebrochen"))

    # Gewichtung nach Horizont; Signale mit Gewicht 0 spielen keine Rolle und werden nicht gezeigt
    weights = p.h["weights"]
    for s in sig:
        s.weight = weights.get(s.name, 1.0)
    a.signals = [s for s in sig if s.weight > 0]
    return a


# ---------- Empfehlung ----------

@dataclass
class Recommendation:
    symbol: str
    action: str  # "Kaufen prüfen" | "Halten / beobachten" | "Reduzieren prüfen"
    emoji: str
    combined: float
    technical: float
    sentiment: float | None
    reasons: list[str]
    profile: str = ""
    stop: float | None = None
    target: float | None = None
    crv: float | None = None
    position: dict | None = None
    notes: list[str] = field(default_factory=list)
    trail_pct: float | None = None  # empfohlener Abstand für einen mitlaufenden Stopp in Prozent


def position_size(p: Profile, entry: float, stop: float | None) -> dict | None:
    """Stückzahl, sodass ein Stopp höchstens das Depotrisiko des Profils kostet, begrenzt auf die Höchstposition."""
    if p.portfolio_size <= 0 or stop is None or entry - stop <= 0:
        return None
    R = p.r
    risk_abs = entry - stop
    shares = math.floor(p.portfolio_size * R["risk_per_trade"] / 100 / risk_abs)
    cap = p.portfolio_size * R["max_position"] / 100
    if shares * entry > cap:
        shares = math.floor(cap / entry)
    if shares <= 0:
        return None
    return {"shares": shares, "value": round(shares * entry, 2), "risk": round(shares * risk_abs, 2),
            "risk_pct": R["risk_per_trade"], "max_pct": R["max_position"]}


BUY, HOLD, SELL = "Kaufen prüfen", "Halten / beobachten", "Reduzieren prüfen"
EMOJI = {BUY: "🟢", HOLD: "🟡", SELL: "🔴"}


def recommend(a: Analysis, sentiment: float | None, profile: Profile | None = None) -> Recommendation:
    p = profile or a.profile
    H, R = p.h, p.r
    m = a.metrics
    close = a.last_close
    notes: list[str] = []

    tech = a.normalized
    combined = tech if sentiment is None else (1 - H["news"]) * tech + H["news"] * sentiment

    atr_pct = m.get("atr_pct")
    if R["vol_limit"] and atr_pct and atr_pct > R["vol_limit"]:
        combined -= R["vol_penalty"]
        notes.append(f"Hohe Schwankung (ATR {atr_pct:.1f} % pro Tag) – Abschlag für {R['label'].lower()}e Anleger")
    combined = round(max(-1.0, min(1.0, combined)), 3)

    # Stopp, Ziel, Chance/Risiko
    atr = m.get("atr")
    stop = round(close - H["stop_atr"] * atr, 4) if atr else None
    risk_abs = close - stop if stop is not None else None
    target = None  # langfristig gibt es kein festes Kursziel, nur den Stopp als Absicherung
    if risk_abs and risk_abs > 0 and H["crv_gate"]:
        if a.resistance and a.resistance > close * 1.005:
            target = a.resistance
        else:
            target = round(close + 2 * risk_abs, 4)
    crv = round((target - close) / risk_abs, 2) if target and risk_abs and risk_abs > 0 else None

    sma200 = m.get("sma200")
    below200 = bool(sma200) and close < sma200
    if combined >= R["buy"]:
        action = BUY
        if below200 and R["trend_filter"] == "strict":
            action = HOLD
            notes.append("Konservativ: kein Kauf unterhalb der 200-Tage-Linie")
        elif below200 and R["trend_filter"] == "soft" and combined < R["buy"] + 0.1:
            action = HOLD
            notes.append("Kurs unter der 200-Tage-Linie – für einen Kauf fehlt noch Bestätigung")
        elif H["crv_gate"] and crv is not None and crv < R["min_crv"]:
            action = HOLD
            notes.append(f"Chance/Risiko {crv:.1f} unter {R['min_crv']:.1f} – Widerstand zu nah")
    elif combined <= R["sell"]:
        action = SELL
    else:
        action = HOLD

    position = position_size(p, close, stop) if action == BUY else None

    top = sorted(a.signals, key=lambda s: abs(s.score * s.weight), reverse=True)[:3]
    reasons = [s.text for s in top] + notes
    if sentiment is not None:
        mood = "positiv" if sentiment > 0.15 else "negativ" if sentiment < -0.15 else "neutral"
        reasons.append(f"News-Stimmung {mood} ({sentiment:+.2f})")
    return Recommendation(a.symbol, action, EMOJI[action], combined, tech, sentiment, reasons, p.label,
                          stop, target, crv, position, notes, trail_pct(p, close, atr))


def trail_pct(p: Profile, price: float, atr: float | None) -> float | None:
    """Abstand eines mitlaufenden Stopps: Stopp-Abstand des Horizonts (x-faches der Tagesschwankung) in Prozent,
    auf halbe Prozent gerundet, mindestens 2 %."""
    if not atr or not price:
        return None
    return max(2.0, round(p.h["stop_atr"] * atr / price * 100 * 2) / 2)
