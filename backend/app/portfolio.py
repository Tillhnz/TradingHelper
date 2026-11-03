"""Erfasste Käufe auswerten: Gewinn/Verlust, Hinweise (Stopp, Ziel, Stopp nachziehen) und Verlauf des Depots.

Kaufkurs, Stopp und Ziel einer Position gelten in ihrer Währung (`currency`, leer = Handelswährung des
Börsenplatzes). Für den Gesamtverlauf wird jede Position mit dem Tageskurs in die Depotwährung umgerechnet.
"""

from __future__ import annotations

import math
from datetime import date

import pandas as pd

from . import analysis, market

PERIODS = [(365, "1y"), (730, "2y"), (1825, "5y")]


def position_currency(pos: dict) -> str | None:
    if pos.get("currency"):
        return pos["currency"]
    try:
        return market.symbol_info(pos["symbol"]).get("currency")
    except market.MarketDataError:
        return market.guess_listing(pos["symbol"])[1]


def _period_since(day: str) -> str:
    age = (date.today() - date.fromisoformat(day)).days
    for limit, period in PERIODS:
        if age < limit - 10:
            return period
    return "max"


def cost(pos: dict) -> float:
    return pos["quantity"] * pos["buy_price"] + (pos.get("fees") or 0)


def evaluate(pos: dict, profile: analysis.Profile) -> dict:
    """Aktueller Stand einer Position mit Hinweisen."""
    out = dict(pos)
    ccy = position_currency(pos)
    out["display_currency"] = ccy
    invested = cost(pos)
    out["invested"] = round(invested, 2)
    if pos.get("sell_date"):
        proceeds = pos["quantity"] * pos["sell_price"] - (pos.get("sell_fees") or 0)
        out.update(price=pos["sell_price"], value=round(proceeds, 2), pl=round(proceeds - invested, 2),
                   pl_pct=round((proceeds / invested - 1) * 100, 2) if invested else None, closed=True, hints=[])
        return out
    out["closed"] = False
    hints: list[dict] = []
    try:
        df = market.get_history(pos["symbol"], profile.period, "1d", currency=pos.get("currency") or None)
        a = analysis.analyze(pos["symbol"], df, profile)
        rec = analysis.recommend(a, None)
    except Exception as exc:  # noqa: BLE001
        out.update(price=None, value=None, pl=None, pl_pct=None, hints=[], error=str(exc))
        return out
    price = a.last_close
    value = pos["quantity"] * price
    out.update(price=price, value=round(value, 2), pl=round(value - invested, 2),
               pl_pct=round((value / invested - 1) * 100, 2) if invested else None,
               day_change_pct=a.change_pct_1d, action=rec.action)

    stop, target, buy = pos.get("stop"), pos.get("target"), pos["buy_price"]
    if stop and price <= stop:
        hints.append({"level": "bad", "text": "Stopp erreicht – Verkauf prüfen"})
    if target and price >= target:
        hints.append({"level": "good", "text": "Ziel erreicht – Gewinne sichern oder Stopp nachziehen"})
    atr = a.metrics.get("atr")
    if atr and price > buy:
        trail = price - profile.h["stop_atr"] * atr
        if price - buy > profile.h["stop_atr"] * atr:
            trail = max(trail, buy)  # mindestens Einstand
        if trail > (stop or 0) * 1.005:
            hints.append({"level": "info", "text": f"Stopp nachziehen auf ca. {round(trail, 2)}",
                          "suggested_stop": round(trail, 2)})
    if rec.action == analysis.SELL:
        hints.append({"level": "bad", "text": "Einschätzung: Reduzieren prüfen"})
    if not stop:
        hints.append({"level": "info", "text": "Kein Stopp hinterlegt"})
    out["hints"] = hints
    return out


def _days(idx) -> pd.DatetimeIndex:
    return market._days(idx)


def pl_series(pos: dict, total_ccy: str | None) -> pd.Series:
    """Täglicher Gewinn/Verlust einer Position (ab Kaufdatum) in der Depotwährung."""
    start = pd.Timestamp(pos["buy_date"])
    df = market.get_history(pos["symbol"], _period_since(pos["buy_date"]), "1d", currency=pos.get("currency") or None)
    closes = df["close"].copy()
    closes.index = _days(closes.index)
    closes = closes[~closes.index.duplicated(keep="last")]
    closes = closes[closes.index >= start]
    qty, buy, fees = pos["quantity"], pos["buy_price"], pos.get("fees") or 0
    pl = (closes - buy) * qty - fees
    if pos.get("sell_date"):
        end = pd.Timestamp(pos["sell_date"])
        realized = (pos["sell_price"] - buy) * qty - fees - (pos.get("sell_fees") or 0)
        pl = pl[pl.index < end]
        pl.loc[end] = realized
        pl = pl.sort_index()
    if pl.empty:
        pl = pd.Series([-fees], index=[start])
    ccy = position_currency(pos)
    base, factor = market.base_currency(ccy)
    if base and total_ccy and (base != total_ccy or factor != 1):
        if base != total_ccy:
            rates = market.fx_rates(base, total_ccy, "5y")
            aligned = rates.reindex(rates.index.union(pl.index)).sort_index().ffill().bfill().reindex(pl.index)
            pl = pl * aligned.to_numpy() * factor
        else:
            pl = pl * factor
    return pl


def history(positions: list[dict], total_ccy: str | None) -> dict:
    """Summe Gewinn/Verlust aller Positionen je Tag. Geschlossene Positionen zählen danach mit dem Ergebnis."""
    series, errors = [], {}
    for pos in positions:
        try:
            series.append(pl_series(pos, total_ccy))
        except Exception as exc:  # noqa: BLE001
            errors[pos["symbol"]] = str(exc)
    if not series:
        return {"currency": total_ccy, "points": [], "errors": errors}
    idx = series[0].index
    for s in series[1:]:
        idx = idx.union(s.index)
    total = pd.Series(0.0, index=idx)
    for s in series:
        aligned = s.reindex(idx).ffill()  # nach Verkauf bleibt das Ergebnis stehen
        total = total + aligned.fillna(0.0)  # vor dem Kauf zählt die Position nicht
    points = [{"time": int(t.timestamp()), "value": round(float(v), 2)} for t, v in total.items() if not math.isnan(v)]
    return {"currency": total_ccy, "points": points, "errors": errors}
