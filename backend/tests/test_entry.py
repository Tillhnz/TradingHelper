from app import analysis, entry
from app.analysis import BUY, HOLD, SELL, Analysis, Profile, Recommendation, Signal


def _a(close=100.0, profile=None, **m):
    metrics = {"atr": 2.0, "atr_pct": 2.0, "sma50": 96.0, "sma200": 85.0, "ema9": 101.0, "ema21": 98.0, "rsi": 55.0,
               "hist": 0.5, "bb_lower": 92.0, "bb_mid": 98.0, "bb_pctb": 0.6, "high_52w": 125.0}
    metrics.update(m)
    return Analysis("X", close, 0.3, metrics, [Signal("Trend", 2, "t")], support=94.0, resistance=108.0,
                    profile=profile or Profile())


def _rec(action=HOLD, stop=None, target=None):
    return Recommendation("X", action, "", 0.1, 0.1, None, [], "", stop, target)


def kinds(plan):
    return [s["kind"] for s in plan["setups"]]


def test_uptrend_medium_offers_pullback_and_breakout():
    p = entry.plan(_a(), _rec())
    assert kinds(p) == ["pullback", "breakout"]
    pb, bo = p["setups"]
    assert pb["title"] == "Rücksetzer an die SMA 50" and pb["entry"] == 96.0 and pb["zone"] == [95.0, 97.0]
    assert pb["stop"] == 91.0 and pb["target"] == 108.0 and pb["crv"] == 2.4 and pb["status"] == "wait"
    assert pb["alert"] == {"kind": "price_below", "params": {"value": 97.0}, "interval": "1d", "once": True,
                           "label": "Kurs fällt in die Zone um 96,00"}
    assert bo["entry"] == 108.4 and bo["alert"]["kind"] == "cross_up" and bo["target"] == 125.0
    assert p["summary"].startswith("Abwarten: Rücksetzer an die SMA 50 bei ca. 96,00 (−4,0 %)".replace("−", "-"))
    assert "Ausbruch über 108,00 ab 108,40" in p["summary"]
    assert entry.plan(_a(), _rec(), currency="EUR")["summary"].startswith("Abwarten: Rücksetzer an die SMA 50 bei ca. 96,00 €")
    assert entry.fmt(1234.5, "USD") == "1.234,50 $"


def test_pullback_now_when_price_in_zone():
    p = entry.plan(_a(close=96.5), _rec())
    pb = p["setups"][0]
    assert pb["status"] == "now" and pb["alert"] is None
    assert p["summary"].startswith("Einstieg jetzt möglich: Rücksetzer")


def test_short_uses_ema21_long_uses_tranches():
    short = entry.plan(_a(profile=Profile("short")), _rec())
    assert short["setups"][0]["title"] == "Rücksetzer an die EMA 21"
    long = entry.plan(_a(profile=Profile("long")), _rec())
    titles = [s["title"] for s in long["setups"] if s["kind"] == "pullback"]
    assert titles == ["Teilkauf 1 an der SMA 50", "Teilkauf 2 an der SMA 200"]
    assert all(s["target"] is None and s["ok"] for s in long["setups"])


def test_conservative_downtrend_only_waits():
    a = _a(close=80.0, sma50=82.0, sma200=90.0, hist=-0.3, profile=Profile(risk="conservative"))
    a.resistance = 86.0
    p = entry.plan(a, _rec(SELL))
    assert p["setups"] == []
    assert p["wait"][0]["title"].startswith("Schlusskurs über der 200-Tage-Linie")
    assert p["wait"][0]["alert"]["kind"] == "price_cross_ma"
    assert any(w["alert"]["kind"] == "macd_cross_up" for w in p["wait"])
    assert p["summary"].startswith("Kein Einstieg – Signale negativ.")


def test_aggressive_rebound_when_oversold():
    a = _a(close=92.5, sma50=95.0, sma200=99.0, rsi=28.0, bb_pctb=0.05, hist=-0.2, profile=Profile(risk="aggressive"))
    p = entry.plan(a, _rec())
    rb = next(s for s in p["setups"] if s["kind"] == "rebound")
    assert rb["status"] == "now" and rb["stop"] == 90.5 and rb["target"] == 98.0
    assert rb["alert"]["kind"] == "rsi_above"
    cons = entry.plan(_a(close=92.5, sma50=95.0, sma200=99.0, rsi=28.0, bb_pctb=0.05,
                         profile=Profile(risk="conservative")), _rec())
    assert "rebound" not in kinds(cons)


def test_crv_filter_marks_setup_not_ok():
    a = _a(profile=Profile(risk="conservative"))
    a.resistance = 101.0  # Ziel kaum über dem Rücksetzer-Einstieg
    pb = entry.plan(a, _rec())["setups"][0]
    assert pb["ok"] is False and "Chance/Risiko" in pb["problem"]


def test_buy_now_and_position(uptrend):
    p = Profile(portfolio_size=10_000)
    a = analysis.analyze("X", uptrend, p)
    rec = analysis.recommend(a, None)
    plan = entry.plan(a, rec)
    if rec.action == BUY:
        assert plan["setups"][0]["kind"] == "now"
    good = [s for s in plan["setups"] if s["ok"]]
    assert all(s["position"] is None or s["position"]["shares"] > 0 for s in good)
    pb = entry.plan(_a(profile=p), _rec())["setups"][0]
    # 1 % von 10.000 = 100 € Risiko / 5 € Abstand = 20 Stück à 96 € = 1.920 € → Deckel 10 % = 1.000 € → 10 Stück
    assert pb["position"]["shares"] == 10


def test_overheated_suggests_waiting():
    p = entry.plan(_a(rsi=78.0), _rec())
    assert any("Überhitzung" in w["title"] and w["alert"]["kind"] == "rsi_below" for w in p["wait"])


def test_no_atr():
    p = entry.plan(_a(atr=None), _rec())
    assert p["setups"] == [] and "Zu wenig" in p["summary"]
