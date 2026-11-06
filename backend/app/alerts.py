"""Alarmregeln ähnlich TradingView: Kurs-, Indikator- und Crossing-Bedingungen."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import quote

import pandas as pd

from . import indicators as ind
from . import market, notify
from .config import Settings
from .storage import Alert, Storage

log = logging.getLogger(__name__)


@dataclass
class AlertKind:
    name: str
    description: str
    params: dict  # Parametername -> Default (None = Pflicht)
    check: Callable[[pd.DataFrame, dict], str | None]


CUR = "§C"  # Platzhalter für das Währungszeichen, wird in evaluate() ersetzt
SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "CHF": "CHF"}


def _n(x: float, digits: int = 2) -> str:
    """Deutsche Schreibweise: 1.234,56"""
    return f"{x:,.{digits}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def _p(x) -> str:
    """Kurs mit Währung, z. B. 82,44 €"""
    return f"{_n(float(x))}{CUR}"


def _last(s: pd.Series) -> float:
    return float(s.iloc[-1])


def _price_above(d, p):
    if _last(d["close"]) > p["value"]:
        return f"Kurs {_p(_last(d['close']))} über {_p(p['value'])}"


def _price_below(d, p):
    if _last(d["close"]) < p["value"]:
        return f"Kurs {_p(_last(d['close']))} unter {_p(p['value'])}"


def _cross_up(d, p):
    if ind.crossed_above(d["close"], p["value"]):
        return f"Kurs steigt über {_p(p['value'])} (jetzt {_p(_last(d['close']))})"


def _cross_down(d, p):
    if ind.crossed_below(d["close"], p["value"]):
        return f"Kurs fällt unter {_p(p['value'])} (jetzt {_p(_last(d['close']))})"


def _pct_change(d, p):
    chg = (_last(d["close"]) / float(d["close"].iloc[-2]) - 1) * 100
    if abs(chg) >= p["value"]:
        return f"Tagesbewegung {'+' if chg > 0 else ''}{_n(chg)} % (Schwelle ±{_n(p['value'], 1)} %)"


def _rsi_above(d, p):
    r = ind.rsi(d["close"], int(p["period"]))
    if ind.crossed_above(r, p["value"]):
        return f"RSI({p['period']}) steigt über {p['value']} ({_n(_last(r), 1)})"


def _rsi_below(d, p):
    r = ind.rsi(d["close"], int(p["period"]))
    if ind.crossed_below(r, p["value"]):
        return f"RSI({p['period']}) fällt unter {p['value']} ({_n(_last(r), 1)})"


def _macd_cross_up(d, p):
    m = ind.macd(d["close"])
    if ind.crossed_above(m["macd"], m["signal"]):
        return "MACD kreuzt Signallinie nach oben"


def _macd_cross_down(d, p):
    m = ind.macd(d["close"])
    if ind.crossed_below(m["macd"], m["signal"]):
        return "MACD kreuzt Signallinie nach unten"


def _ma(d: pd.DataFrame, kind: str, n: int) -> pd.Series:
    return ind.ema(d["close"], n) if kind == "ema" else ind.sma(d["close"], n)


def _ma_cross_up(d, p):
    fast, slow = _ma(d, p["type"], int(p["fast"])), _ma(d, p["type"], int(p["slow"]))
    if ind.crossed_above(fast, slow):
        t = p["type"].upper()
        return f"{t}{p['fast']} kreuzt {t}{p['slow']} nach oben" + (
            " (Golden Cross)" if (int(p["fast"]), int(p["slow"])) == (50, 200) else "")


def _ma_cross_down(d, p):
    fast, slow = _ma(d, p["type"], int(p["fast"])), _ma(d, p["type"], int(p["slow"]))
    if ind.crossed_below(fast, slow):
        t = p["type"].upper()
        return f"{t}{p['fast']} kreuzt {t}{p['slow']} nach unten" + (
            " (Death Cross)" if (int(p["fast"]), int(p["slow"])) == (50, 200) else "")


def _price_cross_ma(d, p):
    m = _ma(d, p["type"], int(p["period"]))
    t = f"{p['type'].upper()}{p['period']}"
    if ind.crossed_above(d["close"], m):
        return f"Kurs kreuzt {t} nach oben ({_p(_last(d['close']))})"
    if ind.crossed_below(d["close"], m):
        return f"Kurs kreuzt {t} nach unten ({_p(_last(d['close']))})"


def _bb_break(d, p):
    b = ind.bollinger(d["close"], int(p["period"]), float(p["k"]))
    if ind.crossed_above(d["close"], b["bb_upper"]):
        return "Ausbruch über oberes Bollinger-Band"
    if ind.crossed_below(d["close"], b["bb_lower"]):
        return "Ausbruch unter unteres Bollinger-Band"


def _volume_spike(d, p):
    avg = ind.sma(d["volume"], 20).iloc[-2]
    if avg and _last(d["volume"]) >= p["factor"] * avg:
        return f"Volumen {_n(_last(d['volume']) / avg, 1)}× über 20-Tage-Schnitt"


def _new_high(d, p):
    n = int(p["lookback"])
    if len(d) > n and _last(d["high"]) >= d["high"].iloc[-n - 1:-1].max():
        return f"Neues {n}-Perioden-Hoch ({_p(_last(d['high']))})"


def _new_low(d, p):
    n = int(p["lookback"])
    if len(d) > n and _last(d["low"]) <= d["low"].iloc[-n - 1:-1].min():
        return f"Neues {n}-Perioden-Tief ({_p(_last(d['low']))})"


KINDS: dict[str, AlertKind] = {k.name: k for k in [
    AlertKind("price_above", "Kurs liegt über Wert", {"value": None}, _price_above),
    AlertKind("price_below", "Kurs liegt unter Wert", {"value": None}, _price_below),
    AlertKind("cross_up", "Kurs kreuzt Wert nach oben", {"value": None}, _cross_up),
    AlertKind("cross_down", "Kurs kreuzt Wert nach unten", {"value": None}, _cross_down),
    AlertKind("pct_change", "Bewegung ggü. Vorperiode ≥ ±X %", {"value": 5.0}, _pct_change),
    AlertKind("rsi_above", "RSI kreuzt Schwelle nach oben", {"value": 70, "period": 14}, _rsi_above),
    AlertKind("rsi_below", "RSI kreuzt Schwelle nach unten", {"value": 30, "period": 14}, _rsi_below),
    AlertKind("macd_cross_up", "MACD kreuzt Signal nach oben", {}, _macd_cross_up),
    AlertKind("macd_cross_down", "MACD kreuzt Signal nach unten", {}, _macd_cross_down),
    AlertKind("ma_cross_up", "Schneller MA kreuzt langsamen nach oben",
              {"fast": 50, "slow": 200, "type": "sma"}, _ma_cross_up),
    AlertKind("ma_cross_down", "Schneller MA kreuzt langsamen nach unten",
              {"fast": 50, "slow": 200, "type": "sma"}, _ma_cross_down),
    AlertKind("price_cross_ma", "Kurs kreuzt gleitenden Durchschnitt", {"period": 200, "type": "sma"},
              _price_cross_ma),
    AlertKind("bb_break", "Ausbruch aus Bollinger-Bändern", {"period": 20, "k": 2.0}, _bb_break),
    AlertKind("volume_spike", "Volumen ≥ Faktor × 20er-Schnitt", {"factor": 2.0}, _volume_spike),
    AlertKind("new_high", "Neues N-Perioden-Hoch", {"lookback": 52}, _new_high),
    AlertKind("new_low", "Neues N-Perioden-Tief", {"lookback": 52}, _new_low),
]}


def build_params(kind: str, given: dict) -> dict:
    if kind not in KINDS:
        raise ValueError(f"Unbekannter Alarmtyp '{kind}'. Verfügbar: {', '.join(KINDS)}")
    spec = KINDS[kind].params
    params = {}
    for key, default in spec.items():
        if key in given and given[key] is not None:
            val = given[key]
            if key == "type":
                val = str(val).lower()
                if val not in ("sma", "ema"):
                    raise ValueError("type muss 'sma' oder 'ema' sein")
            else:
                val = float(val)
            params[key] = val
        elif default is None:
            raise ValueError(f"Parameter '{key}' ist für {kind} erforderlich")
        else:
            params[key] = default
    return params


def evaluate(alert: Alert, df: pd.DataFrame, currency: str | None = None) -> str | None:
    msg = KINDS[alert.kind].check(df, alert.params)
    if msg:
        msg = msg.replace(CUR, f" {SYMBOLS.get(currency, currency)}" if currency else "")
    return msg


def label(symbol: str) -> str:
    """Lesbarer Name statt internem Kürzel (bei gettex sonst die ISIN)."""
    try:
        info = market.symbol_info(symbol)
    except Exception:  # noqa: BLE001
        return symbol
    return info.get("name") or info.get("ticker") or symbol


def _in_cooldown(alert: Alert, minutes: int) -> bool:
    if not alert.last_triggered:
        return False
    last = datetime.fromisoformat(alert.last_triggered)
    return datetime.now(timezone.utc) - last < timedelta(minutes=minutes)


# yfinance-Periode passend zum Intervall (Intraday-Daten sind begrenzt verfügbar)
_PERIOD_FOR = {"1m": "5d", "5m": "1mo", "15m": "1mo", "30m": "1mo", "1h": "3mo", "1d": "2y", "1wk": "5y"}


def _native(symbol: str) -> str | None:
    try:
        return market.symbol_info(symbol).get("currency")
    except Exception:  # noqa: BLE001
        return None


def check_all(storage: Storage, settings: Settings, send: bool = True) -> list[dict]:
    """Prüft alle aktiven Alarme. Gibt ausgelöste Alarme zurück."""
    fired: list[dict] = []
    frames: dict[tuple[str, str], pd.DataFrame] = {}
    for alert in storage.alerts(active_only=True):
        if _in_cooldown(alert, settings.alert_cooldown_minutes):
            continue
        key = (alert.symbol, alert.interval, alert.currency)
        try:
            if key not in frames:
                frames[key] = market.get_history(alert.symbol, _PERIOD_FOR.get(alert.interval, "1y"), alert.interval,
                                                 currency=alert.currency or None)
            ccy = alert.currency or _native(alert.symbol)
            msg = evaluate(alert, frames[key], ccy)
        except Exception as exc:  # noqa: BLE001
            log.warning("Alarm #%s (%s) nicht prüfbar: %s", alert.id, alert.symbol, exc)
            continue
        if not msg:
            continue
        storage.mark_triggered(alert, msg)
        fired.append({"id": alert.id, "symbol": alert.symbol, "name": label(alert.symbol), "kind": alert.kind,
                      "message": msg})
        if send:
            name = label(alert.symbol)
            when = {"1d": "Tageskurs", "1wk": "Wochenkurs"}.get(alert.interval, alert.interval)
            notify.send(settings, f"Alarm: {name}", f"**{name}**: {msg} ({when})",
                        priority="high", tags=["chart_with_upwards_trend"], path=f"/chart/{quote(alert.symbol)}")
    return fired
