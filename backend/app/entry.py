"""Einstiegsplan: ab welchem Kurs ein Einstieg sinnvoll ist und auf welche Signale man warten sollte.

Je nach Anlagestrategie entstehen bis zu vier Arten von Einstiegen:

- Sofort        wenn die Einschätzung schon „Kaufen prüfen“ lautet
- Rücksetzer    Kauf in einer Zone an einer Unterstützung im intakten Aufwärtstrend
                (kurzfristig EMA 21, mittelfristig SMA 50 oder Unterstützung, langfristig Teilkäufe an SMA 50 und SMA 200)
- Ausbruch      Kauf, wenn der Kurs über den nächsten Widerstand steigt (nicht konservativ im Abwärtstrend)
- Rebound       nur offensiv bzw. ausgewogen-kurzfristig: Gegenbewegung aus überverkauftem Zustand, enger Stopp

Dazu kommen Warte-Signale (z. B. „Schlusskurs über der 200-Tage-Linie“, „MACD dreht nach oben“). Jeder Punkt hat
einen passenden Alarm, den die Oberfläche mit einem Klick anlegt.
"""

from __future__ import annotations

from .analysis import BUY, SELL, Analysis, Profile, Recommendation, position_size

NOW, WAIT = "now", "wait"


def _p(x: float | None) -> float | None:
    if x is None:
        return None
    return round(x, 2) if abs(x) >= 1 else round(x, 4)


SYMBOL = {"EUR": "€", "USD": "$", "GBP": "£"}


def fmt(x: float | None, ccy: str | None = None) -> str:
    """Deutsche Schreibweise, z. B. 1.234,50 €."""
    if x is None:
        return "–"
    text = f"{x:,.2f}" if abs(x) >= 1 else f"{x:,.4f}"
    text = text.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{text} {SYMBOL.get(ccy, ccy)}" if ccy else text


def _setup(p: Profile, kind: str, title: str, entry: float, zone: tuple[float, float], stop: float,
           target: float | None, why: str, alert: dict | None, close: float) -> dict:
    H, R = p.h, p.r
    risk = entry - stop
    crv = round((target - entry) / risk, 2) if target and risk > 0 else None
    ok, problem = True, None
    if H["crv_gate"] and crv is not None and crv < R["min_crv"]:
        ok, problem = False, f"Chance/Risiko {crv:.1f} unter {R['min_crv']:.1f} – für dein Profil zu wenig"
    status = NOW if zone[0] <= close <= zone[1] else WAIT
    return {
        "kind": kind, "title": title, "status": status, "ok": ok, "problem": problem, "why": why,
        "entry": _p(entry), "zone": [_p(zone[0]), _p(zone[1])], "stop": _p(stop), "target": _p(target), "crv": crv,
        "distance_pct": round((entry / close - 1) * 100, 1),
        "position": position_size(p, entry, stop) if ok else None,
        "alert": alert if status == WAIT else None,
    }


def plan(a: Analysis, rec: Recommendation, profile: Profile | None = None, currency: str | None = None) -> dict:
    p = profile or a.profile
    H, R = p.h, p.r
    m = a.metrics
    close = a.last_close
    atr = m.get("atr")
    if not atr:
        return {"summary": "Zu wenig Kursdaten für einen Einstiegsplan.", "setups": [], "wait": []}
    k = H["stop_atr"]
    sma50, sma200, ema21, ema9 = m.get("sma50"), m.get("sma200"), m.get("ema21"), m.get("ema9")
    rsi, hist = m.get("rsi"), m.get("hist")
    if sma200:
        uptrend = close > sma200 and (sma50 or 0) > sma200
    else:
        uptrend = sma50 is not None and close > sma50
    below200 = bool(sma200) and close < sma200

    def target_for(entry: float, stop: float) -> float | None:
        if not H["crv_gate"]:
            return None  # langfristig kein festes Kursziel
        if a.resistance and a.resistance > entry * 1.005:
            return a.resistance
        return entry + 2 * (entry - stop)

    setups: list[dict] = []

    # Sofort-Einstieg
    if rec.action == BUY and rec.stop:
        setups.append(_setup(p, "now", "Einstieg zum aktuellen Kurs", close, (close - 0.25 * atr, close + 0.25 * atr),
                             rec.stop, rec.target, "Die Einschätzung lautet bereits „Kaufen prüfen“.", None, close))

    # Rücksetzer im Aufwärtstrend
    if uptrend and rec.action != SELL:
        if p.horizon == "short":
            levels = [("EMA 21", ema21)]
        elif p.horizon == "long":
            levels = [("SMA 50", sma50), ("SMA 200", sma200)]
        else:
            levels = [("SMA 50", sma50), ("Unterstützung", a.support)]
        candidates = [(name, lv) for name, lv in levels if lv and lv - 0.5 * atr <= close]
        if p.horizon != "long":  # kurz/mittel: nur die nächstgelegene Marke unter dem Kurs
            candidates = sorted(candidates, key=lambda x: close - x[1])[:1]
        for i, (name, lv) in enumerate(candidates):
            zone = (lv - 0.5 * atr, lv + 0.5 * atr)
            stop = lv - k * atr
            if p.horizon == "long":
                title = f"Teilkauf {i + 1} an der {name}"
                why = "Langfristig lohnt Staffeln: erste Hälfte an der 50-Tage-Linie, zweite bei einem tieferen Rücksetzer."
            else:
                title = f"Rücksetzer an die {name}"
                why = "Im Aufwärtstrend günstiger einsteigen, wenn der Kurs an eine Unterstützung zurückkommt."
            alert = {"kind": "price_below", "params": {"value": _p(zone[1])}, "interval": "1d", "once": True,
                     "label": f"Kurs fällt in die Zone um {fmt(lv, currency)}"}
            setups.append(_setup(p, "pullback", title, lv, zone, stop, target_for(lv, stop), why, alert, close))

    # Ausbruch über den Widerstand
    near_res = a.resistance and a.resistance > close and a.resistance / close - 1 <= 0.12
    if near_res and not (below200 and R["trend_filter"] == "strict") and rec.action != SELL:
        entry = a.resistance + 0.2 * atr
        stop = entry - k * atr
        hi = m.get("high_52w")
        target = None
        if H["crv_gate"]:
            target = hi if hi and hi > entry * 1.02 else entry + 2 * (entry - stop)
        alert = {"kind": "cross_up", "params": {"value": _p(entry)}, "interval": "1d", "once": True,
                 "label": f"Kurs steigt über {fmt(entry, currency)}"}
        setups.append(_setup(p, "breakout", f"Ausbruch über {fmt(a.resistance, currency)}", entry, (entry, entry + 0.5 * atr), stop,
                             target, "Erst kaufen, wenn der Widerstand fällt – am besten mit Schlusskurs darüber und "
                             "erhöhtem Volumen. Nicht hinterherlaufen, wenn der Kurs schon weit darüber ist.", alert, close))

    # Rebound aus überverkauftem Zustand (Gegentrend)
    counter = p.risk == "aggressive" or (p.risk == "balanced" and p.horizon == "short")
    oversold = (rsi is not None and rsi < 35) or (m.get("bb_pctb") is not None and m["bb_pctb"] < 0.15)
    if counter and oversold and m.get("bb_lower") and m.get("bb_mid"):
        lv = m["bb_lower"]
        entry = min(close, lv + 0.5 * atr)
        stop = entry - 1.0 * atr
        alert = {"kind": "rsi_above", "params": {"value": 30, "period": 14}, "interval": "1d", "once": True,
                 "label": "RSI steigt wieder über 30"}
        s = _setup(p, "rebound", "Rebound vom unteren Bollinger-Band", entry, (lv - 0.3 * atr, lv + 0.5 * atr), stop,
                   m["bb_mid"], "Gegentrend-Einstieg mit engem Stopp, Ziel die Mitte der Bänder. Am sichersten, "
                   "wenn der RSI wieder über 30 dreht.", alert, close)
        s["alert"] = alert  # Bestätigungs-Alarm auch anbieten, wenn der Kurs schon in der Zone ist
        setups.append(s)

    # Warte-Signale
    wait: list[dict] = []
    if below200:
        wait.append({"title": f"Schlusskurs über der 200-Tage-Linie ({fmt(sma200, currency)})",
                     "why": "Unter der 200-Tage-Linie ist der übergeordnete Trend abwärts gerichtet."
                            + (" Für dein konservatives Profil ist das Voraussetzung." if p.risk == "conservative" else ""),
                     "alert": {"kind": "price_cross_ma", "params": {"period": 200, "type": "sma"}, "interval": "1d",
                               "once": True, "label": "Kurs kreuzt SMA 200"}})
    if p.horizon == "long" and sma50 and sma200 and sma50 < sma200:
        wait.append({"title": "Golden Cross (SMA 50 steigt über SMA 200)",
                     "why": "Klassisches Signal für den Beginn eines langfristigen Aufwärtstrends.",
                     "alert": {"kind": "ma_cross_up", "params": {"fast": 50, "slow": 200, "type": "sma"}, "interval": "1d",
                               "once": True, "label": "Golden Cross"}})
    if p.horizon != "long" and hist is not None and hist < 0:
        wait.append({"title": "MACD kreuzt die Signallinie nach oben",
                     "why": "Zeigt, dass das Momentum wieder nach oben dreht.",
                     "alert": {"kind": "macd_cross_up", "params": {}, "interval": "1d", "once": True,
                               "label": "MACD kreuzt nach oben"}})
    if p.horizon == "short" and ema9 and ema21 and ema9 < ema21:
        wait.append({"title": "EMA 9 kreuzt EMA 21 nach oben",
                     "why": "Kurzfristiges Trendwende-Signal.",
                     "alert": {"kind": "ma_cross_up", "params": {"fast": 9, "slow": 21, "type": "ema"}, "interval": "1d",
                               "once": True, "label": "EMA 9 über EMA 21"}})
    if rsi is not None and rsi > 70:
        wait.append({"title": f"Überhitzung abbauen lassen (RSI {rsi:.0f} fällt unter 60)",
                     "why": "Nach starkem Anstieg folgt oft eine Verschnaufpause – ein Rücksetzer ist meist der bessere Einstieg.",
                     "alert": {"kind": "rsi_below", "params": {"value": 60, "period": 14}, "interval": "1d", "once": True,
                               "label": "RSI fällt unter 60"}})

    return {"summary": _summary(rec, setups, wait, currency), "setups": setups, "wait": wait}


def _summary(rec: Recommendation, setups: list[dict], wait: list[dict], ccy: str | None) -> str:
    good = [s for s in setups if s["ok"]]
    now = [s for s in good if s["status"] == NOW]
    if now:
        s = now[0]
        return f"Einstieg jetzt möglich: {s['title']} (Stopp {fmt(s['stop'], ccy)})."
    waiting = sorted((s for s in good if s["status"] == WAIT), key=lambda s: abs(s["distance_pct"]))
    if waiting:
        parts = []
        for s in waiting[:2]:
            how = f"bei ca. {fmt(s['entry'], ccy)}" if s["kind"] != "breakout" else f"ab {fmt(s['entry'], ccy)}"
            dist = f"{s['distance_pct']:+.1f}".replace(".", ",")
            parts.append(f"{s['title']} {how} ({dist} %)")
        return "Abwarten: " + " oder ".join(parts) + "."
    if wait:
        lead = "Kein Einstieg – Signale negativ." if rec.action == SELL else "Noch kein Einstieg."
        return f"{lead} Warten auf: {wait[0]['title']}."
    if setups:
        return "Einstiege vorhanden, aber Chance/Risiko passt nicht zu deinem Profil."
    return "Kein klares Einstiegssignal – beobachten."
