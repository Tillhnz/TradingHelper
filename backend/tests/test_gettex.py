import pandas as pd
import pytest

from app import gettex, market

SNAP = {
    "instrument": {"entityType": "STOCK", "entityValue": "82849", "name": "SAP", "isin": "DE0007164600", "symbol": "SAP"},
    "quoteList": {"list": [
        {"market": {"name": "Xetra", "codeMarket": "_GER", "idNotation": 1}, "isoCurrency": "EUR", "last": 204.4},
        {"market": {"name": "gettex", "codeMarket": "_TRO", "idNotation": 120499220}, "isoCurrency": "EUR",
         "last": 205.1, "open": 208.6, "high": 209.0, "low": 203.05, "volume": 10, "totalVolume": 5000, "previousLast": 208.45,
         "codeQualityPrice": "RLT",
         "datetimeLast": "2026-11-03T15:23:57.947+00:00"},
    ]},
}
# 2026-10-29, -30, 2026-11-02 jeweils 12:00 UTC
EOD = {"datetimeLast": [1793275200, 1793361600, 1793620800], "first": [200.0, 201.0, 207.0],
       "high": [202.0, 205.0, 209.0], "low": [199.0, 200.0, 206.0], "last": [201.0, 204.0, 208.45],
       "volume": [1000.0, 1100.0, 1200.0]}


TAS: dict = {}


@pytest.fixture
def fake(monkeypatch):
    gettex._SNAP.clear()
    gettex._EOD.clear()
    gettex._TAS.clear()
    TAS.clear()
    market._CACHE.clear()
    market._INFO.clear()
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        if path.endswith("/snapshot"):
            if "/instruments/STOCK/" in path:
                return SNAP
            raise gettex.GettexError("404", 404)
        if "eod_history" in path:
            return EOD
        if "times_and_sales" in path:
            return TAS.get((params or {}).get("startDate", "heute"), {})
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
    assert df.iloc[-1]["high"] == 209.0 and df.iloc[-1]["low"] == 203.05 and df.iloc[-1]["volume"] == 5000
    eod_call = next(c for c in fake if "eod_history" in c[0])
    assert eod_call[1]["idNotation"] == 120499220 and eod_call[0] == "/instruments/STOCK/82849/eod_history"


def test_weekly_and_no_intraday(fake):
    wk = gettex.history("DE0007164600.GTX", "1y", "1wk")
    assert len(wk) == 2 and wk.iloc[-1]["close"] == 205.1
    with pytest.raises(gettex.GettexError):
        gettex.history("DE0007164600.GTX", "1mo", "1h")  # Minutenkerzen nur für 1 oder 5 Tage
    assert market.intraday_limit("DE0007164600.GTX") == "5d" and market.intraday_limit("SAP.DE") is None


def test_intraday_from_trades(fake, monkeypatch):
    import datetime as dt
    today = pd.Timestamp.now(tz="Europe/Berlin").normalize()
    # an einem Wochenende auf den letzten Freitag zurückgehen
    while today.weekday() >= 5:
        today -= pd.Timedelta(days=1)
    t0 = int((today + pd.Timedelta(hours=9)).timestamp())
    trades = {"datetimePrice": [t0, t0 + 60, t0 + 240, t0 + 400], "price": [10.0, 11.0, 9.5, 10.5],
              "volume": [1.0, 2.0, 3.0, 4.0]}
    if today.date() == dt.datetime.now(tz=today.tz).date():
        TAS["heute"] = trades
    else:
        TAS[today.date().isoformat()] = trades
    df = gettex.history("DE0007164600.GTX", "1d", "5m")
    assert list(df["open"]) == [10.0, 10.5] and list(df["high"]) == [11.0, 10.5]
    assert list(df["low"]) == [9.5, 10.5] and list(df["volume"]) == [6.0, 4.0]
    assert str(df.index.tz) == "Europe/Berlin"


def test_live_quote_with_bid_ask(fake):
    SNAP["quoteList"]["list"][1].update(bid=205.0, ask=205.2, datetimeBid="2026-11-03T15:24:10.000+00:00")
    q = market.live("DE0007164600.GTX")
    assert q["price"] == 205.1 and q["bid"] == 205.0 and q["ask"] == 205.2 and q["currency"] == "EUR"
    assert q["change_pct"] == pytest.approx((205.1 / 208.45 - 1) * 100, abs=1e-3)


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


def test_eod_cache_independent_of_period(fake, monkeypatch):
    # Echte Bereichszuordnung: 1mo und 1y liegen beide im Bereich Y1 und teilen sich den Zwischenspeicher
    monkeypatch.setattr(gettex, "_range_for", lambda period: (
        "Y1", pd.Timestamp("2026-10-01" if period == "1mo" else "2026-01-01").date()))
    gettex.history("DE0007164600.GTX", "1mo", "1d")
    eod = [c for c in fake if "eod_history" in c[0]]
    assert eod[-1][1]["startDate"] == gettex.range_start("Y1").isoformat()  # ganzer Bereich, nicht nur 1 Monat
    full = gettex.history("DE0007164600.GTX", "1y", "1d")
    assert len([c for c in fake if "eod_history" in c[0]]) == 1  # aus dem Zwischenspeicher
    assert len(full) == 4  # alle Tageskurse plus heute


def test_snapshot_uses_instruments_path_and_survives_throttling(monkeypatch):
    """onvista bremst /stocks/…/snapshot mit 429 – wir nehmen /instruments/STOCK/…, bei Störung den letzten Stand."""
    import time as _t
    gettex._SNAP.clear()
    seen = []

    def throttled(path, params=None):
        seen.append(path)
        if path.startswith("/stocks/"):
            raise gettex.GettexError("zu viele Anfragen", 429)
        if path.startswith("/instruments/STOCK/"):
            return SNAP
        raise gettex.GettexError("404", 404)

    monkeypatch.setattr(gettex, "_get", throttled)
    assert gettex.snapshot("DE0007164600")["instrument"]["name"] == "SAP"
    assert seen[0] == "/instruments/STOCK/ISIN:DE0007164600/snapshot"

    # Alles gebremst: letzter Stand (jünger als ein Tag) statt Fehler
    gettex._SNAP["DE0007164600"] = (_t.time() - 600, SNAP)
    monkeypatch.setattr(gettex, "_get", lambda path, params=None: (_ for _ in ()).throw(gettex.GettexError("429", 429)))
    assert gettex.snapshot("DE0007164600") is SNAP
    gettex._SNAP.clear()
    with pytest.raises(gettex.GettexError) as e:
        gettex.snapshot("DE0007164600")
    assert e.value.status == 429 and "nicht gefunden" not in str(e.value)


def test_pause_after_429(monkeypatch):
    """Nach einem 429 fragt TradeHelper eine Weile gar nicht mehr an – sonst verlängert sich die Sperre."""
    calls = []

    class R:
        def __init__(self, code):
            self.status_code, self.ok = code, code == 200

        def json(self):
            return {"instrument": {"name": "X"}}

    codes = iter([429, 200])
    monkeypatch.setattr(gettex.requests, "get", lambda *a, **k: (calls.append(a[0]), R(next(codes)))[1])
    monkeypatch.setattr(gettex, "_STATE", {"last": 0.0, "cool_until": 0.0, "cool": 60.0})
    with pytest.raises(gettex.GettexError):
        gettex._get("/x")
    assert gettex.throttle_status()["paused"] and gettex._STATE["cool"] == 120
    with pytest.raises(gettex.GettexError) as e:
        gettex._get("/y")
    assert e.value.status == 429 and len(calls) == 1  # in der Pause keine Anfrage
    gettex._STATE["cool_until"] = 0
    assert gettex._get("/z")["instrument"]["name"] == "X"
    assert gettex._STATE["cool"] == 60 and len(calls) == 2
