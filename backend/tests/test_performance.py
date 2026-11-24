from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app import market, performance
from app.analysis import Profile


def test_xirr_simple_year():
    r = performance.xirr([(date(2025, 1, 1), -1000), (date(2026, 1, 1), 1100)])
    assert r == pytest.approx(0.10, abs=1e-4)


def test_xirr_multiple_flows_and_none():
    flows = [(date(2023, 1, 1), -1000), (date(2023, 7, 1), -1000), (date(2024, 1, 1), 2200)]
    r = performance.xirr(flows)
    # 1000 ein Jahr, 1000 ein halbes Jahr → ca. 13 %
    assert 0.12 < r < 0.14
    assert performance.xirr([(date(2024, 1, 1), -1000)]) is None
    assert performance.xirr([(date(2024, 1, 1), 1000), (date(2024, 2, 1), 1000)]) is None


def test_twr_ignores_deposits():
    idx = pd.date_range("2024-01-01", periods=4, freq="D")
    values = pd.Series([100.0, 110.0, 220.0, 242.0], index=idx)
    flows = pd.Series([100.0, 0.0, 100.0, 0.0], index=idx)  # zweite Einzahlung an Tag 3
    r = performance.twr(values, flows)
    total = float((1 + r).prod() - 1)
    # Tag 2 +10 %, Tag 3: Kauf zählt zum Tagesbeginn → 220 / (110 + 100) − 1, Tag 4 +10 %
    assert total == pytest.approx(1.1 * (220 / 210) * 1.1 - 1, rel=1e-6)


def test_twr_rebuy_after_almost_empty_depot():
    """Fast alles verkauft, dann groß nachgekauft, 2 % über dem Schlusskurs: darf nicht als −400 % zählen."""
    idx = pd.date_range("2026-01-01", periods=4, freq="D")
    values = pd.Series([10000.0, 50.0, 9850.0, 9850.0], index=idx)
    flows = pd.Series([10000.0, -9950.0, 10000.0, 0.0], index=idx)
    idx_ = (1 + performance.twr(values, flows)).cumprod()
    assert idx_.iloc[-1] == pytest.approx((9850 / 10050), rel=1e-6)
    assert idx_.min() > 0.9


def test_shadow_sells_same_share():
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    prices = pd.Series([10.0, 10.0, 20.0], index=idx)
    values = pd.Series([1000.0, 500.0, 500.0], index=idx)   # Tag 2: Hälfte verkauft (500 €)
    flows = pd.Series([1000.0, -500.0, 0.0], index=idx)
    val, own = performance.shadow(prices, values, flows)
    assert own.tolist() == pytest.approx([1000, -500, 0])
    assert val.tolist() == pytest.approx([1000, 500, 1000])
    # Depot stark gestiegen, Vergleich nicht: verkauft trotzdem nur den Anteil, nie mehr als vorhanden
    values2 = pd.Series([1000.0, 0.0, 0.0], index=idx)
    flows2 = pd.Series([1000.0, -3000.0, 0.0], index=idx)
    val2, own2 = performance.shadow(prices, values2, flows2)
    assert own2[1] == pytest.approx(-1000) and val2[-1] == 0


def test_max_drawdown():
    idx = pd.date_range("2024-01-01", periods=5, freq="D")
    dd, frm, to = performance.max_drawdown(pd.Series([1.0, 1.2, 0.9, 1.0, 1.3], index=idx))
    assert dd == pytest.approx(0.9 / 1.2 - 1)
    assert frm == "2024-01-02" and to == "2024-01-03"


def _series(start: date, days: int, start_price: float, daily: float) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=days)
    close = start_price * (1 + daily) ** np.arange(days)
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1000}, index=idx)


@pytest.fixture
def fake_market(monkeypatch):
    start = date.today() - timedelta(days=500)
    data = {
        "WIN.DE": _series(start, 360, 100, 0.002),   # steigt kräftig
        "LOSE.DE": _series(start, 360, 50, -0.001),  # fällt
        "EUNL.DE": _series(start, 360, 80, 0.0005),  # Weltmarkt: leicht steigend
        "EXS1.DE": _series(start, 360, 120, 0.0),
    }

    def hist(sym, period="1y", interval="1d", currency=None):
        if sym not in data:
            raise market.MarketDataError("nicht da")
        return data[sym]

    monkeypatch.setattr(market, "get_history", hist)
    monkeypatch.setattr(market, "symbol_info", lambda s: {"symbol": s, "currency": "EUR", "name": s})
    monkeypatch.setattr(market, "cached_info", lambda s: {"name": f"Name {s}"})
    return data


def test_compute_full(fake_market):
    days = fake_market["WIN.DE"].index
    d = lambda i: str(days[i].date())  # noqa: E731
    win_close = fake_market["WIN.DE"]["close"]
    lose_close = fake_market["LOSE.DE"]["close"]
    positions = [
        {"id": 1, "symbol": "WIN.DE", "quantity": 10, "buy_price": float(win_close.iloc[10]), "buy_date": d(10), "fees": 1,
         "currency": "EUR", "sell_price": None, "sell_date": None, "sell_fees": 0, "stop": 90},
        {"id": 2, "symbol": "LOSE.DE", "quantity": 20, "buy_price": float(lose_close.iloc[20]), "buy_date": d(20), "fees": 1,
         "currency": "EUR", "sell_price": float(lose_close.iloc[200]), "sell_date": d(200), "sell_fees": 1},
        {"id": 3, "symbol": "WIN.DE", "quantity": 5, "buy_price": float(win_close.iloc[50]), "buy_date": d(50), "fees": 1,
         "currency": "EUR", "sell_price": float(win_close.iloc[100]), "sell_date": d(100), "sell_fees": 1},
        {"id": 4, "symbol": "GONE.XX", "quantity": 1, "buy_price": 10, "buy_date": d(30), "fees": 0, "currency": "EUR",
         "sell_price": None, "sell_date": None, "sell_fees": 0},
    ]
    r = performance.compute(positions, "EUR", Profile("medium"), bench_symbols=["EUNL.DE", "EXS1.DE"])
    assert r["lots"] == 4 and r["missing"] == ["GONE.XX"]
    assert r["irr"] is not None and r["irr"] > 0
    assert r["twr"] > 0
    assert r["fees"] == pytest.approx(5)
    labels = {b["label"]: b for b in r["benchmarks"]}
    assert set(labels) == {"MSCI World", "DAX"}
    # gleiches Geld in einen flachen DAX-ETF → Gewinn ≈ 0 (bis auf Gebühren)
    assert abs(labels["DAX"]["gain"]) < 5
    assert labels["MSCI World"]["diff_value"] is not None
    b = r["behavior"]
    assert b["buys"] == 4 and b["sells"] == 2 and b["closed"] == 2
    assert b["win_rate"] == 50
    assert b["hold_win_days"] is not None and b["hold_loss_days"] is not None
    assert len(r["curve"]["dates"]) == len(r["curve"]["portfolio"]) == len(r["curve"]["EUNL.DE"])
    assert r["positions"][0]["symbol"] == "WIN.DE"
    assert r["years"] and r["insights"]
    assert all(t["level"] in ("good", "warn", "bad", "info") for t in r["insights"])


def test_compute_empty():
    r = performance.compute([], "EUR")
    assert r["empty"] is True and r["lots"] == 0
