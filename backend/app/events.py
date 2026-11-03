"""Vergangene Entscheidungspunkte für den Chart: an welchen Kerzen Kauf- oder Verkaufssignale auftraten.

Welche Signale gezeigt werden, hängt vom Anlagehorizont ab (dieselbe Logik wie bei der Gewichtung):
kurzfristig MACD, RSI und EMA 9/21, mittelfristig MACD, RSI und 200-Tage-Linie, langfristig 200-Tage-Linie
sowie Golden/Death Cross.
"""

from __future__ import annotations

import pandas as pd

from .analysis import Profile

BUY, SELL = "buy", "sell"


def _up(a: pd.Series, b) -> pd.Series:
    b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
    return (a > b) & (a.shift() <= b.shift())


def _down(a: pd.Series, b) -> pd.Series:
    b = b if isinstance(b, pd.Series) else pd.Series(b, index=a.index)
    return (a < b) & (a.shift() >= b.shift())


def signal_events(d: pd.DataFrame, profile: Profile | None = None, limit: int = 60) -> list[dict]:
    """d: Kursdaten mit Indikatoren (indicators.add_all). Ergebnis zeitlich sortiert, höchstens `limit` Einträge."""
    p = profile or Profile()
    rules: list[tuple[pd.Series, str, str, str, str]] = []  # (Maske, Art, Richtung, Kurztext, Erklärung)
    if p.horizon in ("short", "medium"):
        rules += [
            (_up(d["macd"], d["signal"]), "macd", BUY, "MACD", "MACD kreuzt Signallinie nach oben"),
            (_down(d["macd"], d["signal"]), "macd", SELL, "MACD", "MACD kreuzt Signallinie nach unten"),
            (_up(d["rsi"], 30), "rsi", BUY, "RSI 30", "RSI verlässt überverkauften Bereich"),
            (_down(d["rsi"], 70), "rsi", SELL, "RSI 70", "RSI verlässt überkauften Bereich"),
        ]
    if p.horizon == "short":
        rules += [
            (_up(d["ema9"], d["ema21"]), "ema", BUY, "EMA", "EMA 9 kreuzt EMA 21 nach oben"),
            (_down(d["ema9"], d["ema21"]), "ema", SELL, "EMA", "EMA 9 kreuzt EMA 21 nach unten"),
        ]
    if p.horizon in ("medium", "long"):
        rules += [
            (_up(d["close"], d["sma200"]), "sma200", BUY, "SMA200", "Schlusskurs über der 200-Tage-Linie"),
            (_down(d["close"], d["sma200"]), "sma200", SELL, "SMA200", "Schlusskurs unter der 200-Tage-Linie"),
            (_up(d["sma50"], d["sma200"]), "golden", BUY, "Golden Cross", "SMA 50 kreuzt SMA 200 nach oben"),
            (_down(d["sma50"], d["sma200"]), "death", SELL, "Death Cross", "SMA 50 kreuzt SMA 200 nach unten"),
        ]
    events = []
    for mask, kind, side, short, text in rules:
        for ts in d.index[mask.fillna(False).to_numpy()]:
            events.append({"time": int(pd.Timestamp(ts).timestamp()), "kind": kind, "side": side,
                           "label": short, "text": text})
    events.sort(key=lambda e: e["time"])
    return events[-limit:]
