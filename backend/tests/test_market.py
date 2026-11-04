import pandas as pd
import pytest

from app import market
from app.storage import Storage


@pytest.mark.parametrize("symbol,expected", [
    ("AAPL", ("USA", "USD")), ("SAP.DE", ("Xetra", "EUR")), ("APC.F", ("Frankfurt", "EUR")),
    ("NESN.SW", ("SIX Swiss", "CHF")), ("VOD.L", ("London", "GBp")), ("^GDAXI", ("Index", None)),
    ("BTC-EUR", ("Krypto", "EUR")), ("BRK-B", ("USA", "USD")), ("EURUSD=X", ("Devisen", "USD")),
])
def test_guess_listing(symbol, expected):
    assert market.guess_listing(symbol) == expected


def _frame(days, closes, tz="America/New_York"):
    idx = pd.DatetimeIndex(pd.to_datetime(days)).tz_localize(tz)
    return pd.DataFrame({"open": closes, "high": closes, "low": closes, "close": closes, "volume": [100] * len(closes)},
                        index=idx)


def test_convert_uses_rate_of_each_day():
    df = _frame(["2026-01-05", "2026-01-06", "2026-01-07"], [100.0, 110.0, 120.0])
    # Wechselkurs fehlt am 7. → Vortageskurs
    rates = pd.Series([0.9, 0.8], index=pd.to_datetime(["2026-01-05", "2026-01-06"]))
    out = market.convert_history(df, "USD", "EUR", rates=rates)
    assert out["close"].round(4).tolist() == [90.0, 88.0, 96.0]
    assert out["volume"].tolist() == [100, 100, 100]
    assert df["close"].tolist() == [100.0, 110.0, 120.0]  # Original unverändert


def test_convert_intraday_and_minor_units():
    df = _frame(["2026-01-05 15:30", "2026-01-05 16:30"], [1000.0, 1010.0], tz="Europe/London")
    rates = pd.Series([1.2], index=pd.to_datetime(["2026-01-05"]))
    out = market.convert_history(df, "GBp", "EUR", rates=rates)
    assert out["close"].round(4).tolist() == [12.0, 12.12]
    assert market.convert_history(df, "GBp", "GBP")["close"].tolist() == [10.0, 10.1]


def test_convert_noop_cases():
    df = _frame(["2026-01-05"], [100.0])
    assert market.convert_history(df, "EUR", "EUR") is df
    assert market.convert_history(df, None, "EUR") is df  # Index ohne Währung
    assert market.convert_history(df, "USD", None) is df
    assert market.shown_currency(None, "EUR") is None
    assert market.shown_currency("USD", None) == "USD"
    assert market.shown_currency("USD", "EUR") == "EUR"


def test_search_parsing(monkeypatch):
    class FakeSearch:
        def __init__(self, q, **kw):
            self.quotes = [
                {"symbol": "AAPL", "shortname": "Apple Inc.", "exchDisp": "NASDAQ", "quoteType": "EQUITY", "typeDisp": "Equity"},
                {"symbol": "APC.DE", "longname": "Apple Inc.", "exchDisp": "XETRA", "quoteType": "EQUITY"},
                {"symbol": "XYZ", "quoteType": "OPTION"},
            ]

    class FakeYf:
        Search = FakeSearch

    monkeypatch.setattr(market, "_yf", lambda: FakeYf)
    monkeypatch.setattr(market.gettex, "search", lambda q, limit=6: [{"symbol": "US0378331005.GTX", "name": "Apple"}])
    res = market.search("apple")
    assert res[0]["symbol"] == "US0378331005.GTX"
    res = res[1:]
    assert [r["symbol"] for r in res] == ["AAPL", "APC.DE"]
    assert res[1] == {"symbol": "APC.DE", "name": "Apple Inc.", "exchange": "XETRA", "type": "EQUITY", "currency": "EUR"}
    assert market.search("  ") == []

    def boom(q, limit=6):
        raise market.gettex.GettexError("offline")

    monkeypatch.setattr(market.gettex, "search", boom)
    assert [r["symbol"] for r in market.search("apple")] == ["AAPL", "APC.DE"]


def test_storage_migrates_old_schema(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    c = sqlite3.connect(db)
    c.executescript("""
        CREATE TABLE watchlist (symbol TEXT PRIMARY KEY, note TEXT DEFAULT '', added_at TEXT NOT NULL);
        CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, kind TEXT NOT NULL,
            params TEXT NOT NULL DEFAULT '{}', interval TEXT NOT NULL DEFAULT '1d', once INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1, last_triggered TEXT, created_at TEXT NOT NULL);
        INSERT INTO watchlist VALUES ('AAPL', '', '2026-01-01');
        INSERT INTO alerts(symbol, kind, created_at) VALUES ('AAPL', 'macd_cross_up', '2026-01-01');
    """)
    c.commit()
    c.close()
    st = Storage(db)
    w = st.watchlist()[0]
    assert w["symbol"] == "AAPL" and w["currency"] is None
    assert st.alerts()[0].currency == ""
    st.add_symbol("APC.DE", "", "Apple", "XETRA", "EUR")
    assert st.watchlist()[1]["exchange"] == "XETRA"
    st.add_symbol("APC.DE", "Notiz")  # Metadaten bleiben erhalten
    assert st.watchlist()[1]["currency"] == "EUR" and st.watchlist()[1]["note"] == "Notiz"
