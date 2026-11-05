"""Erfasste Käufe auswerten: Gewinn/Verlust, Hinweise (Stopp, Ziel, Stopp nachziehen) und Verlauf des Depots.

Kaufkurs, Stopp und Ziel einer Position gelten in ihrer Währung (`currency`, leer = Handelswährung des
Börsenplatzes). Für den Gesamtverlauf wird jede Position mit dem Tageskurs in die Depotwährung umgerechnet.
"""

from __future__ import annotations

import math
from datetime import date

import pandas as pd

from . import analysis, market
from .entry import fmt

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
    try:
        inf = market.symbol_info(pos["symbol"])
        out["ticker"], out["name"] = inf.get("ticker"), inf.get("name")
    except market.MarketDataError:
        out["ticker"], out["name"] = None, None
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
    qty, fees = pos["quantity"], pos.get("fees") or 0
    atr = a.metrics.get("atr")
    out["stop_base"] = stop
    out["trail_suggest_pct"] = analysis.trail_pct(profile, price, atr)

    # Mitlaufender Stopp: x % unter dem höchsten Schlusskurs seit dem Kauf, nie unter dem eingetragenen Stopp
    if pos.get("trail_pct"):
        days = _days(df.index)
        since = df["close"][days >= pd.Timestamp(pos["buy_date"])]
        high = max(float(since.max()) if len(since) else buy, buy)
        dyn = round(high * (1 - pos["trail_pct"] / 100), 4)
        out["trail_high"], out["trail_stop"] = round(high, 4), dyn
        if dyn > (stop or 0):
            stop = dyn
            out["stop"] = dyn
            out["stop_dynamic"] = True

    # Was passiert bis Stopp bzw. Ziel – ab jetzt gerechnet und als Ergebnis gegenüber dem Einstand
    if stop:
        out["risk_to_stop"] = round((price - stop) * qty, 2)
        out["pl_at_stop"] = round((stop - buy) * qty - fees, 2)
    if target:
        out["chance_to_target"] = round((target - price) * qty, 2)
        out["pl_at_target"] = round((target - buy) * qty - fees, 2)
    if stop and price <= stop:
        hints.append({"level": "bad", "text": "Stopp erreicht – Verkauf prüfen"})

    hints.extend(target_hints(pos, profile, a, rec, price, target, ccy))

    if pos.get("trail_pct"):
        if out.get("stop_dynamic") and (pos.get("stop") or 0) < stop:
            hints.append({"level": "info", "text": f"Stopp läuft mit: {fmt(stop, ccy)} ({fmt_pct(pos['trail_pct'])} unter dem "
                                                   f"Höchstkurs {fmt(out['trail_high'], ccy)})"})
    elif atr and price > buy:
        trail = price - profile.h["stop_atr"] * atr
        if price - buy > profile.h["stop_atr"] * atr:
            trail = max(trail, buy)  # mindestens Einstand
        if trail > (stop or 0) * 1.005:
            hints.append({"level": "info", "text": f"Stopp nachziehen auf ca. {fmt(trail, ccy)}",
                          "suggested_stop": round(trail, 2)})
    if rec.action == analysis.SELL:
        hints.append({"level": "bad", "text": "Einschätzung: Reduzieren prüfen"})
    if not stop:
        hints.append({"level": "info", "text": "Kein Stopp hinterlegt"})
    out["hints"] = hints
    return out


def fmt_pct(x: float) -> str:
    return f"{x:g}".replace(".", ",") + " %"


def suggested_target(profile: analysis.Profile, a: analysis.Analysis, price: float) -> tuple[float | None, str]:
    """Kursziel aus heutiger Sicht: nächster Widerstand oberhalb, sonst 2 × Stopp-Abstand über dem Kurs.
    Langfristig gibt es kein festes Ziel (dort zählt der Trend, der Stopp sichert ab)."""
    if not profile.h["crv_gate"]:
        return None, ""
    atr = a.metrics.get("atr")
    if a.resistance and a.resistance > price * 1.01:
        return round(a.resistance, 2), "nächster Widerstand"
    if atr:
        return round(price + 2 * profile.h["stop_atr"] * atr, 2), "kein Widerstand in Sicht, Ziel aus der üblichen Schwankung"
    return None, ""


def target_hints(pos: dict, profile: analysis.Profile, a: analysis.Analysis, rec, price: float,
                 target: float | None, ccy: str | None) -> list[dict]:
    """Ziel an die aktuelle Lage anpassen: erreicht und Trend intakt → anheben; Signale kippen → senken."""
    sugg, why = suggested_target(profile, a, price)
    out: list[dict] = []
    if target and price >= target:
        if rec.action == analysis.SELL or not sugg:
            out.append({"level": "good", "text": "Ziel erreicht – Signale drehen, Gewinne sichern oder Stopp eng nachziehen"
                        if rec.action == analysis.SELL else "Ziel erreicht – Gewinne sichern oder Stopp nachziehen"})
        else:
            out.append({"level": "good", "text": f"Ziel erreicht, Trend intakt – neues Ziel {fmt(sugg, ccy)} ({why})",
                        "suggested_target": sugg, "reason": "reached"})
    elif target and sugg and sugg > target * 1.03 and rec.action == analysis.BUY:
        out.append({"level": "info", "text": f"Ziel anheben auf {fmt(sugg, ccy)} – Signale positiv ({why})",
                    "suggested_target": sugg, "reason": "raise"})
    elif target and sugg and sugg < target * 0.97 and rec.action == analysis.SELL:
        out.append({"level": "warn", "text": f"Ziel senken auf {fmt(sugg, ccy)} – Signale negativ, {why} liegt tiefer",
                    "suggested_target": sugg, "reason": "lower"})
    elif not target and sugg:
        out.append({"level": "info", "text": f"Kein Ziel hinterlegt – Vorschlag {fmt(sugg, ccy)} ({why})",
                    "suggested_target": sugg, "reason": "missing"})
    return out


def watch(storage, settings, send=None) -> list[str]:
    """Für die Alarmprüfung: meldet einmalig, wenn ein (mitlaufender) Stopp erreicht ist oder sich das Ziel ändern
    sollte. Der zuletzt gemeldete Stand steht in watch_state, damit nichts doppelt kommt."""
    import json

    from . import notify

    send = send or (lambda title, text: notify.send(settings, title, text, tags=["dart"]))
    profile = analysis.profile_from(settings)
    sent = []
    for pos in storage.positions(open_only=True):
        try:
            ev = evaluate(pos, profile)
        except Exception:  # noqa: BLE001
            continue
        if ev.get("error") or ev.get("price") is None:
            continue
        try:
            state = json.loads(pos.get("watch_state") or "{}")
        except ValueError:
            state = {}
        name = ev.get("name") or ev.get("ticker") or pos["symbol"]
        ccy = ev["display_currency"]
        msgs = []
        stop = ev.get("stop")
        if stop and ev["price"] <= stop and state.get("stop_hit") != stop:
            kind = "mitlaufender Stopp" if ev.get("stop_dynamic") else "Stopp"
            msgs.append(f"**{name}**: {kind} {fmt(stop, ccy)} erreicht (Kurs {fmt(ev['price'], ccy)}) – Verkauf prüfen")
            state["stop_hit"] = stop
        sugg = next((h for h in ev["hints"] if h.get("suggested_target") and h.get("reason") != "missing"), None)
        last = state.get("target_sent")
        if sugg and (not last or abs(sugg["suggested_target"] / last - 1) > 0.03):
            msgs.append(f"**{name}**: {sugg['text']}")
            state["target_sent"] = sugg["suggested_target"]
        if msgs:
            text = "\n".join(msgs)
            send(f"Depot: {name}", text)
            storage.update_position(pos["id"], {"watch_state": json.dumps(state)})
            sent.append(text)
    return sent


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


def summarize(items: list[dict], action: str | None = None) -> dict | None:
    """Bestand eines Werts aus allen Käufen: Stückzahl, Durchschnittskurs, G/V, realisiert und ein Rat für Halter.

    items: Ergebnisse von evaluate() für dasselbe Symbol.
    """
    if not items:
        return None
    open_ = [p for p in items if not p["closed"]]
    closed = [p for p in items if p["closed"]]
    ccys = {p["display_currency"] for p in items}
    ccy = next(iter(ccys)) if len(ccys) == 1 else None
    out: dict = {"currency": ccy, "mixed_currency": len(ccys) > 1, "lots": len(open_), "closed_lots": len(closed),
                 "realized": round(sum(p["pl"] or 0 for p in closed), 2) if ccy else None}
    if not open_:
        out.update(shares=0, advice=None)
        return out
    shares = sum(p["quantity"] for p in open_)
    invested = sum(p["invested"] for p in open_)
    priced = [p for p in open_ if p.get("value") is not None]
    value = sum(p["value"] for p in priced) if len(priced) == len(open_) else None
    out.update(
        shares=shares, invested=round(invested, 2), avg_price=round(invested / shares, 4) if shares else None,
        price=open_[-1].get("price"), value=round(value, 2) if value is not None else None,
        pl=round(value - invested, 2) if value is not None else None,
        pl_pct=round((value / invested - 1) * 100, 2) if value is not None and invested else None,
        stop=min((p["stop"] for p in open_ if p.get("stop")), default=None),
        target=max((p["target"] for p in open_ if p.get("target")), default=None),
        since=min(p["buy_date"] for p in open_),
    )
    for key in ("risk_to_stop", "pl_at_stop", "chance_to_target", "pl_at_target"):
        vals = [p[key] for p in open_ if p.get(key) is not None]
        out[key] = round(sum(vals), 2) if vals and ccy else None
    out["lots_without_stop"] = sum(1 for p in open_ if not p.get("stop"))
    if not ccy:
        for k in ("invested", "avg_price", "value", "pl"):
            out[k] = None
    out["advice"] = advice(open_, action or open_[-1].get("action"))
    return out


def advice(open_: list[dict], action: str | None) -> dict:
    """Ein klarer Satz für den Halter, abgeleitet aus Einschätzung und den Hinweisen der Käufe."""
    texts = [h["text"] for p in open_ for h in p.get("hints", [])]
    if any(t.startswith("Stopp erreicht") for t in texts):
        return {"level": "bad", "text": "Stopp erreicht – Verkauf prüfen"}
    if action == analysis.SELL:
        return {"level": "bad", "text": "Signale negativ – Bestand reduzieren oder Stopp eng setzen"}
    reached = next((h for p in open_ for h in p.get("hints", []) if h.get("reason") == "reached"), None)
    if reached:
        return {"level": "good", "text": reached["text"]}
    if any(t.startswith("Ziel erreicht") for t in texts):
        return {"level": "good", "text": "Ziel erreicht – Gewinne sichern oder Stopp nachziehen"}
    change = next((h for p in open_ for h in p.get("hints", []) if h.get("reason") in ("raise", "lower")), None)
    trail = next((h for p in open_ for h in p.get("hints", []) if h.get("suggested_stop")), None)
    if action == analysis.BUY:
        return {"level": "good", "text": "Halten – Nachkauf möglich" + (f"; {trail['text']}" if trail else "")}
    if change:
        return {"level": "warn" if change["reason"] == "lower" else "info", "text": f"Halten – {change['text']}"}
    if trail:
        return {"level": "info", "text": f"Halten – {trail['text']}"}
    if not all(p.get("stop") for p in open_):
        return {"level": "info", "text": "Halten – Stopp hinterlegen, um Verluste zu begrenzen"}
    return {"level": "info", "text": "Halten – derzeit kein Handlungsbedarf"}
