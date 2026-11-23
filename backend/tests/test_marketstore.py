import time
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app import market, marketstore


def _bars(days: int, end: date | None = None, start_price: float = 100.0) -> pd.DataFrame:
    end = end or date.today()
    idx = pd.bdate_range(end=pd.Timestamp(end), periods=days)
    close = start_price + np.arange(days) * 0.1
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                         "volume": np.full(days, 1000.0)}, index=idx.tz_localize("America/New_York"))


@pytest.fixture
def store(tmp_path, monkeypatch):
    st = marketstore.open_store(tmp_path / "market.db")
    market._INFO.clear()
    market._CACHE.clear()
    calls = []

    def fake_fetch(symbol, days=None, start=None):
        calls.append((symbol, days, start))
        df = _bars(1300)
        if start:
            df = df[market._days(df.index) >= pd.Timestamp(start)]
        return df

    monkeypatch.setattr(market, "_fetch_daily", fake_fetch)
    yield st, calls
    marketstore.close_store()


def test_store_roundtrip(tmp_path):
    st = marketstore.MarketStore(tmp_path / "m.db")
    df = _bars(5)
    assert st.put_daily("aapl", df, span_days=10) == 5
    got = st.daily("AAPL")
    assert len(got) == 5 and got.index.tz is None
    assert st.series("AAPL")["span_days"] == 10
    st.put_quote("AAPL", {"price": 1.5})
    assert st.quote("aapl")[0]["price"] == 1.5
    st.put("info:X", {"a": 1})
    assert st.get("info:X") == {"a": 1}
    assert st.get("info:X", max_age=-1) is None
    assert st.stats()["candles"] == 5


def test_first_fetch_then_served_from_store(store):
    st, calls = store
    df = market._raw_history("AAPL", "1y", "1d")
    assert len(calls) == 1 and calls[0][1] == market.FIRST_SPAN
    assert 240 < len(df) < 270
    # weitere Zeiträume bis 5 Jahre: kein Netzwerk
    market._raw_history("AAPL", "2y", "1d")
    market._raw_history("AAPL", "5d", "1d")
    w = market._raw_history("AAPL", "1y", "1wk")
    assert len(calls) == 1
    assert 50 <= len(w) <= 54


def test_stale_data_refreshes_incrementally(store):
    st, calls = store
    market._raw_history("AAPL", "1y", "1d")
    with st._conn() as c:
        c.execute("UPDATE series SET fetched_at=?", (time.time() - 10 * 3600,))
    with market.fresh_reads():
        market._raw_history("AAPL", "1y", "1d")
    assert len(calls) == 2 and calls[1][2] is not None  # nur ab Start nachgeladen


def test_adjustment_triggers_full_reload(store, monkeypatch):
    st, calls = store
    market._raw_history("AAPL", "1y", "1d")
    with st._conn() as c:
        c.execute("UPDATE series SET fetched_at=?", (time.time() - 10 * 3600,))
        c.execute("UPDATE candles SET close=close*2")  # so, als hätte die Quelle rückwirkend angepasst
    with market.fresh_reads():
        df = market._raw_history("AAPL", "1y", "1d")
    assert calls[-1][1] == market.FIRST_SPAN  # komplett neu geholt
    assert abs(df["close"].iloc[0] - _bars(1300)["close"].iloc[-len(df)]) < 1


def test_quote_overlays_today(store):
    st, _ = store
    df = market._raw_history("AAPL", "1mo", "1d")
    last = df.index[-1]
    t = int(pd.Timestamp(last).tz_localize("Europe/Berlin").timestamp()) + 12 * 3600
    st.put_quote("AAPL", {"price": 999.0, "time": t})
    df2 = market._raw_history("AAPL", "1mo", "1d")
    assert df2["close"].iloc[-1] == 999.0 and df2["high"].iloc[-1] == 999.0
    # Kurs eines neuen Handelstags hängt eine Kerze an
    nxt = last + pd.offsets.BDay(1)
    t2 = int(pd.Timestamp(nxt).tz_localize("Europe/Berlin").timestamp()) + 12 * 3600
    st.put_quote("AAPL", {"price": 5.0, "time": t2})
    df3 = market._raw_history("AAPL", "1mo", "1d")
    assert df3.index[-1] == nxt and df3["close"].iloc[-1] == 5.0


def test_live_reads_quote_cache(store, monkeypatch):
    st, _ = store
    st.put_quote("AAPL", {"symbol": "AAPL", "price": 10.0, "previous_close": 8.0, "native": "USD", "time": 1})
    monkeypatch.setattr(market, "fetch_live", lambda s: pytest.fail("sollte aus dem Speicher kommen"))
    q = market.live("AAPL")
    assert q["price"] == 10.0 and q["change_pct"] == 25.0 and q["currency"] == "USD"


def test_without_store_falls_back(monkeypatch):
    marketstore.close_store()
    market._CACHE.clear()
    monkeypatch.setattr(market, "_fetch_daily", lambda s, days=None, start=None: _bars(600))
    df = market._raw_history("MSFT", "1y", "1d")
    assert len(df) < 300
    assert market._days(df.index)[0] >= pd.Timestamp(date.today() - timedelta(days=367))
