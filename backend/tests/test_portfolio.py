from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app import analysis, events, indicators, market, portfolio
from app.analysis import Profile


def _daily(start: date, closes) -> pd.DataFrame:
    idx = pd.DatetimeIndex([pd.Timestamp(start + timedelta(days=i)) for i in range(len(closes))]).tz_localize("Europe/Berlin")
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1000.0}, index=idx)


@pytest.fixture
def fake_market(monkeypatch):
    start = date.today() - timedelta(days=59)
    frames = {"AAA": _daily(start, np.linspace(100, 130, 60)), "BBB": _daily(start, np.linspace(50, 40, 60))}
    monkeypatch.setattr(market, "get_history", lambda s, *a, **k: frames[s.upper()])
    monkeypatch.setattr(market, "symbol_info", lambda s: {"currency": "EUR" if s.upper() == "AAA" else "USD"})
    rates = pd.Series(0.5, index=pd.date_range(start - timedelta(days=5), periods=80, freq="D"))
    monkeypatch.setattr(market, "fx_rates", lambda frm, to, period="1y": rates)
    return start


def _pos(symbol, buy_date, price, qty=10, **kw):
    return {"id": 1, "symbol": symbol, "quantity": qty, "buy_price": price, "buy_date": buy_date.isoformat(),
            "fees": kw.get("fees", 0), "currency": kw.get("currency", ""), "stop": kw.get("stop"),
            "target": kw.get("target"), "note": "", "sell_price": kw.get("sell_price"),
            "sell_date": kw.get("sell_date"), "sell_fees": 0}


def test_evaluate_open_position(fake_market):
    pos = _pos("AAA", fake_market, 100.0, qty=10, fees=5, stop=95.0, target=125.0)
    ev = portfolio.evaluate(pos, Profile())
    assert ev["price"] == 130.0 and ev["value"] == 1300.0 and ev["invested"] == 1005.0
    assert ev["pl"] == 295.0 and ev["pl_pct"] == pytest.approx(29.35, abs=0.01)
    texts = [h["text"] for h in ev["hints"]]
    assert any("Ziel erreicht" in t for t in texts)
    assert any(t.startswith("Stopp nachziehen") for t in texts)


def test_evaluate_closed_and_stop_hit(fake_market):
    closed = portfolio.evaluate(_pos("AAA", fake_market, 100.0, sell_price=110.0, sell_date=date.today().isoformat()),
                                Profile())
    assert closed["closed"] and closed["pl"] == 100.0
    hit = portfolio.evaluate(_pos("BBB", fake_market, 50.0, stop=42.0), Profile())
    assert hit["pl"] == -100.0 and any("Stopp erreicht" in h["text"] for h in hit["hints"])


def test_history_sums_and_converts(fake_market):
    late = fake_market + timedelta(days=30)
    h = portfolio.history([_pos("AAA", fake_market, 100.0), _pos("BBB", late, 45.0)], "EUR")
    pts = h["points"]
    assert h["currency"] == "EUR" and pts[0]["value"] == 0.0
    # Ende: AAA (130−100)×10 = 300 €; BBB (40−45)×10 = −50 $ × 0,5 = −25 €
    assert pts[-1]["value"] == pytest.approx(275.0, abs=0.01)
    assert len(pts) == 60


def test_history_keeps_realized_after_sale(fake_market):
    sell = fake_market + timedelta(days=10)
    h = portfolio.history([_pos("AAA", fake_market, 100.0, sell_price=105.0, sell_date=sell.isoformat())], "EUR")
    assert h["points"][-1]["value"] == 50.0
    assert len(h["points"]) == 11


def test_signal_events_follow_horizon(uptrend):
    d = indicators.add_all(uptrend)
    short = events.signal_events(d, Profile("short"))
    long = events.signal_events(d, Profile("long"))
    assert {e["kind"] for e in short} <= {"macd", "rsi", "ema"}
    assert {e["kind"] for e in long} <= {"sma200", "golden", "death"}
    assert all(e["side"] in ("buy", "sell") and isinstance(e["time"], int) for e in short)
    assert [e["time"] for e in short] == sorted(e["time"] for e in short)


def test_golden_cross_event():
    from conftest import make_df
    df = make_df(np.r_[np.linspace(200, 100, 230), np.linspace(100, 220, 60)])
    ev = events.signal_events(indicators.add_all(df), Profile("long"))
    assert any(e["kind"] == "golden" for e in ev)


def test_position_size_helper():
    p = Profile(portfolio_size=20_000)
    assert analysis.position_size(p, 100.0, 95.0)["shares"] == 20  # 200 € Risiko / 5 € = 40, Deckel 10 % = 20
    assert analysis.position_size(p, 100.0, None) is None


def test_summarize_lots_and_advice(fake_market):
    p = Profile()
    lots = [portfolio.evaluate(_pos("AAA", fake_market, 100.0, qty=10, stop=95.0), p),
            portfolio.evaluate(_pos("AAA", fake_market + timedelta(days=20), 110.0, qty=10), p),
            portfolio.evaluate(_pos("AAA", fake_market, 100.0, qty=5, sell_price=120.0,
                                    sell_date=date.today().isoformat()), p)]
    s = portfolio.summarize(lots)
    assert s["shares"] == 20 and s["lots"] == 2 and s["closed_lots"] == 1
    assert s["avg_price"] == 105.0 and s["value"] == 2600.0 and s["pl"] == 500.0
    assert s["realized"] == 100.0 and s["stop"] == 95.0 and s["currency"] == "EUR"
    assert s["advice"]["text"].startswith("Halten")


def test_advice_priorities():
    stop_hit = [{"stop": 90, "hints": [{"level": "bad", "text": "Stopp erreicht – Verkauf prüfen"}]}]
    assert portfolio.advice(stop_hit, analysis.BUY)["text"].startswith("Stopp erreicht")
    assert portfolio.advice([{"stop": 90, "hints": []}], analysis.SELL)["level"] == "bad"
    assert portfolio.advice([{"stop": 90, "hints": []}], analysis.BUY)["text"] == "Halten – Nachkauf möglich"
    assert "Stopp hinterlegen" in portfolio.advice([{"stop": None, "hints": []}], analysis.HOLD)["text"]
    assert portfolio.summarize([]) is None


def test_risk_and_chance_fields(fake_market):
    p = Profile()
    ev = portfolio.evaluate(_pos("AAA", fake_market, 100.0, qty=10, fees=5, stop=120.0, target=150.0), p)
    assert ev["risk_to_stop"] == 100.0 and ev["pl_at_stop"] == 195.0
    assert ev["chance_to_target"] == 200.0 and ev["pl_at_target"] == 495.0
    s = portfolio.summarize([ev, portfolio.evaluate(_pos("AAA", fake_market, 110.0, qty=10), p)])
    assert s["risk_to_stop"] == 100.0 and s["chance_to_target"] == 200.0 and s["lots_without_stop"] == 1


def test_trailing_stop_follows_high(fake_market):
    # AAA steigt von 100 auf 130: 5 % mitlaufend → Stopp 123,5, über dem eingetragenen 95
    pos = {**_pos("AAA", fake_market, 100.0, stop=95.0), "trail_pct": 5.0}
    ev = portfolio.evaluate(pos, Profile())
    assert ev["trail_high"] == 130.0 and ev["stop"] == pytest.approx(123.5) and ev["stop_dynamic"]
    assert ev["stop_base"] == 95.0
    assert ev["pl_at_stop"] == pytest.approx((123.5 - 100) * 10)
    assert any(h["text"].startswith("Stopp läuft mit") for h in ev["hints"])
    assert not any(h.get("suggested_stop") for h in ev["hints"])  # kein manuelles Nachziehen nötig
    assert ev["trail_suggest_pct"] >= 2


def test_trail_pct_recommendation():
    p = Profile("medium")
    assert analysis.trail_pct(p, 100.0, 2.0) == 5.0  # 2,5 × 2 / 100
    assert analysis.trail_pct(p, 100.0, 0.1) == 2.0  # Mindestabstand
    assert analysis.trail_pct(p, 100.0, None) is None


def test_target_hints_reached_raise_lower():
    class A:  # Minimal-Analyse
        def __init__(self, res, atr=2.0):
            self.resistance, self.metrics = res, {"atr": atr}

    class R:
        def __init__(self, action):
            self.action = action

    p = Profile("medium")
    reached = portfolio.target_hints({}, p, A(140.0), R(analysis.HOLD), 130.0, 125.0, "EUR")
    assert reached[0]["suggested_target"] == 140.0 and reached[0]["reason"] == "reached"
    raise_ = portfolio.target_hints({}, p, A(150.0), R(analysis.BUY), 120.0, 130.0, "EUR")
    assert raise_[0]["reason"] == "raise" and "anheben" in raise_[0]["text"]
    lower = portfolio.target_hints({}, p, A(124.0), R(analysis.SELL), 120.0, 140.0, "EUR")
    assert lower[0]["reason"] == "lower" and "senken" in lower[0]["text"]
    assert portfolio.target_hints({}, p, A(131.0), R(analysis.HOLD), 120.0, 130.0, "EUR") == []
    assert portfolio.target_hints({}, Profile("long"), A(150.0), R(analysis.BUY), 120.0, 130.0, "EUR") == []
    sold = portfolio.target_hints({}, p, A(140.0), R(analysis.SELL), 130.0, 125.0, "EUR")
    assert "Signale drehen" in sold[0]["text"] and "suggested_target" not in sold[0]


def test_watch_notifies_once(fake_market, tmp_path):
    from app.config import Settings
    from app.storage import Storage
    st = Storage(tmp_path / "w.db")
    st.add_position({"symbol": "BBB", "quantity": 10, "buy_price": 50.0, "buy_date": fake_market.isoformat(),
                     "stop": 42.0, "currency": ""})
    got = []
    send = lambda title, text, path=None: got.append(text)  # noqa: E731
    portfolio.watch(st, Settings(), send)
    assert len(got) == 1 and "Stopp" in got[0]
    portfolio.watch(st, Settings(), send)
    assert len(got) == 1  # nicht doppelt
