import pandas as pd
import pytest

from app import gettex, market

SNAP = {
    "instrument": {"entityType": "STOCK", "entityValue": "82849", "name": "SAP", "isin": "DE0007164600", "symbol": "SAP"},
    "quoteList": {"list": [
        {"market": {"name": "Xetra", "codeMarket": "_GER", "idNotation": 1}, "isoCurrency": "EUR", "last": 204.4},
        {"market": {"name": "gettex", "codeMarket": "_TRO", "idNotation": 120499220}, "isoCurrency": "EUR",
         "last": 205.1, "open": 208.6, "high": 209.0, "low": 203.05, "volume": 5000, "previousLast": 208.45,
         "datetimeLast": "2026-11-03T15:23:57.947+00:00"},
    ]},
}
# 2026-10-29, -30, 2026-11-02 jeweils 12:00 UTC
EOD = {"datetimeLast": [1793275200, 1793361600, 1793620800], "first": [200.0, 201.0, 207.0],
       "high": [202.0, 205.0, 209.0], "low": [199.0, 200.0, 206.0], "last": [201.0, 204.0, 208.45],
       "volume": [1000.0, 1100.0, 1200.0]}


@pytest.fixture
def fake(monkeypatch):
    gettex._SNAP.clear()
    gettex._EOD.clear()
    market._CACHE.clear()
    market._INFO.clear()
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        if path.endswith("/snapshot"):
            if "stocks" in path:
                return SNAP
            raise gettex.GettexError("404")
        if "eod_history" in path:
            return EOD
        if path == "/instruments/query":
            return {"list": [
                {"entityType": "STOCK", "isin": "DE0007164600", "name": "SAP", "symbol": "SAP"},
                {"entityType": "BOND", "isin": "XS1", "name": "Anleihe"},
                {"entityType": "FUND", "isin": "IE00B4L5Y983", "name": "iShares Core MSCI World", "symbol": "EUNL"},
            ]}
        raise AssertionError(path)

    monkeypatch.setattr(gettex, "_get", fake_get)
    monkeypatch.setattr(gettex, "_range_for", lambda period: ("Y1", pd.Timestamp("2026-01-01").date()))
    return calls


def test_symbol_helpers():
    assert gettex.is_gettex("de0007164600.gtx") and not gettex.is_gettex("SAP.DE")
    assert gettex.isin_of("DE0007164600.GTX") == "DE0007164600"
    assert market.guess_listing("DE0007164600.GTX") == ("gettex", "EUR")


def test_info_and_quote(fake):
    inf = gettex.info("DE0007164600.GTX")
    assert inf["name"] == "SAP" and inf["ticker"] == "SAP" and inf["exchange"] == "gettex" and inf["delay_min"] == 0
    assert gettex.quote("DE0007164600.GTX")["price"] == 205.1
    q = market.get_quote("DE0007164600.GTX")
    assert q.price == 205.1 and q.change_pct == pytest.approx((205.1 / 208.45 - 1) * 100)


def test_history_adds_today(fake):
    df = gettex.history("DE0007164600.GTX", "1y", "1d")
    assert list(df["close"]) == [201.0, 204.0, 208.45, 205.1]
    assert df.index[-1] == pd.Timestamp("2026-11-03", tz="Europe/Berlin")
    assert df.iloc[-1]["high"] == 209.0 and df.iloc[-1]["low"] == 203.05
    eod_call = next(c for c in fake if "eod_history" in c[0])
    assert eod_call[1]["idNotation"] == 120499220 and eod_call[0] == "/instruments/STOCK/82849/eod_history"


def test_weekly_and_no_intraday(fake):
    wk = gettex.history("DE0007164600.GTX", "1y", "1wk")
    assert len(wk) == 2 and wk.iloc[-1]["close"] == 205.1
    with pytest.raises(gettex.GettexError):
        gettex.history("DE0007164600.GTX", "1mo", "1h")
    assert not market.supports_intraday("DE0007164600.GTX") and market.supports_intraday("SAP.DE")


def test_not_traded_on_gettex(fake, monkeypatch):
    snap = {"instrument": {"name": "Exot"}, "quoteList": {"list": [{"market": {"codeMarket": "_GER"}}]}}
    with pytest.raises(gettex.GettexError, match="nicht gehandelt"):
        gettex.gettex_quote(snap)


def test_search(fake):
    res = gettex.search("sap")
    assert [r["symbol"] for r in res] == ["DE0007164600.GTX", "IE00B4L5Y983.GTX"]
    assert res[1]["type"] == "ETF/Fonds" and res[0]["default"] is True


def test_market_history_routes_to_gettex(fake):
    df = market.get_history("DE0007164600.GTX", "1y", "1d", currency="EUR")
    assert df["close"].iloc[-1] == 205.1
    assert market.last_trade_time("DE0007164600.GTX") == int(pd.Timestamp("2026-11-03T15:23:57.947Z").timestamp())
