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
