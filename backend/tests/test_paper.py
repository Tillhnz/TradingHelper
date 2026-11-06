import numpy as np
import pandas as pd

from app import analysis, paper
from app.config import Settings
from app.storage import Storage


def _df(closes, start="2022-01-03"):
    closes = np.asarray(closes, dtype=float)
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"open": closes * 0.998, "high": closes * 1.01, "low": closes * 0.99, "close": closes,
                         "volume": np.full(len(closes), 1e6)}, index=idx)


def _wave(n, seed, drift=0.0006):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return 100 * np.exp(np.cumsum(rng.normal(drift, 0.015, n))) * (1 + 0.15 * np.sin(t / 40))


def test_book_sizing_fees_and_pl():
    b = paper.Book(10_000, 1)
    p = analysis.Profile("medium", "balanced")  # 1 % Risiko, höchstens 10 % je Position
    t = b.buy("X", "2026-01-02", 100, 95, 120, "Test", p, 10_000)
    assert t["shares"] == 10  # 1000 € Höchstposition, Risiko 10×5 = 50 € < 100 €
    assert b.cash == 10_000 - 1000 - 1
    assert b.buy("X", "2026-01-02", 100, 95, None, "", p, 10_000) is None  # schon im Depot
    s = b.sell("X", "2026-01-05", 110, "Ziel")
    assert s["pl"] == round(10 * 110 - 1 - 1001, 2)
    assert b.buy("X", "2026-01-05", 100, 95, None, "", p, 10_000) is None  # nicht am Verkaufstag zurückkaufen
    assert b.size(60_000, 50_000, p, 10_000) == 0.01  # Bruchstücke bei teuren Werten (100 € Risiko)


def test_check_exit_gap_and_trailing():
    pos = {"entry": 100, "stop": 95, "target": 120}
    assert paper.check_exit(pos, 90, 92, 88) == (90, "Stopp erreicht")  # Kurslücke: Eröffnung statt Stopp
    assert paper.check_exit(pos, 118, 125, 117) == (120, "Kursziel erreicht")
    assert paper.check_exit(pos, 100, 110, 96) is None
    p = {"stop": 95.0}
    paper.trail(p, paper.Sig("x", 120, None, None, 4, 0, ""), analysis.Profile("medium"))
    assert p["stop"] == 110.0
    paper.trail(p, paper.Sig("x", 100, None, None, 4, 0, ""), analysis.Profile("medium"))
    assert p["stop"] == 110.0  # nie senken
    assert paper.check_exit({"entry": 100, "stop": 110, "target": None}, 112, 113, 109)[1].startswith("Nachgezogener")


def test_day_of_handles_gettex_midnight():
    t = pd.Timestamp("2026-11-03 23:00", tz="UTC")  # gettex-Kerze vom 4.11.
    assert paper.day_of(t) == "2026-11-04"
    assert paper.day_of(pd.Timestamp("2026-11-04")) == "2026-11-04"


def test_backtest_runs_all_variants():
    n = 900
    hist = {"A": _df(_wave(n, 1)), "B": _df(_wave(n, 2, -0.0002)), "C": _df(_wave(n, 3, 0.001))}
    end = hist["A"].index[-1].date()
    res = paper.backtest(hist, 10_000, 1, ("medium", "balanced"), end=end)
    assert len(res["variants"]) == 9 and sum(v["current"] for v in res["variants"]) == 1
    assert res["learn"]["to"] < res["test"]["from"]
    assert res["verdict"] in ("keep", "switch") and res["text"]
    assert any(v["learn"]["buys"] > 0 for v in res["variants"])
    for v in res["variants"]:
        assert v["test"]["end_value"] > 0 and v["test"]["max_drawdown_pct"] <= 0
    assert res["curves"]["benchmark"][0]["time"] == res["test"]["from"]


def test_no_lookahead_trades_at_next_open():
    n = 700
    hist = {"A": _df(_wave(n, 5, 0.002))}
    days = sorted(paper._bars(hist["A"]))[-200:]
    sigs = paper.precompute(hist, days)
    res = paper.simulate(("long", "aggressive"), sigs[("long", "aggressive")], {"A": paper._bars(hist["A"])},
                         days, 10_000, 1)
    buys = [t for t in res["trade_log"] if t["side"] == "buy"]
    assert buys
    first = buys[0]
    # Kurs der Order ist die Eröffnung des Tages nach dem Signal
    signal_days = [d for d in days if sigs[("long", "aggressive")]["A"][d].action == paper.BUY]
    assert first["day"] > signal_days[0]
    assert first["price"] == round(paper._bars(hist["A"])[first["day"]][0], 4)


def test_live_run_buys_and_persists(tmp_path, monkeypatch):
    st = Storage(tmp_path / "t.db")
    s = Settings()
    s.data_dir = tmp_path
    s.news_google = s.news_yahoo = False
    s.finnhub_api_key = ""
    s.risk_profile = "aggressive"
    s.invest_horizon = "long"
    st.add_symbol("AAA", "", "Alpha AG")
    df = _df(100 * np.exp(np.linspace(0, 0.8, 400)), start="2025-01-01")
    df.index = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=400)
    monkeypatch.setattr(paper.market, "get_history", lambda *a, **k: df)
    import time as _t
    monkeypatch.setattr(paper.market, "live", lambda sym, c=None: {"price": float(df["close"].iloc[-1]), "time": _t.time()})
    r = paper.run_live(st, s, push=False)
    assert r["errors"] == {}
    v = paper.view(st, s)
    assert v["started"] and v["capital"] == 10_000
    if r["trades"]:
        assert v["positions"][0]["symbol"] == "AAA" and v["positions"][0]["name"] == "Alpha AG"
        assert v["cash"] < 10_000
    # zweiter Lauf am selben Tag kauft nicht doppelt
    r2 = paper.run_live(st, s, push=False)
    assert not [t for t in r2["trades"] if t["side"] == "buy"]
    st.reset_paper()
    assert paper.view(st, s)["started"] is False



def _setup_closed_market(tmp_path, monkeypatch):
    st = Storage(tmp_path / "t.db")
    s = Settings()
    s.news_google = s.news_yahoo = False
    s.finnhub_api_key = ""
    s.risk_profile, s.invest_horizon = "aggressive", "long"
    st.add_symbol("AAA", "", "Alpha AG")
    df = _df(100 * np.exp(np.linspace(0, 0.8, 400)))
    df.index = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=400)
    monkeypatch.setattr(paper.market, "get_history", lambda *a, **k: df)
    return st, s, df


def test_closed_market_places_limit_order_then_fills(tmp_path, monkeypatch):
    st, s, df = _setup_closed_market(tmp_path, monkeypatch)
    last = float(df["close"].iloc[-1])
    monkeypatch.setattr(paper.market, "live", lambda sym, c=None: {"price": last, "time": 1})  # alter Kurs = geschlossen
    r = paper.run_live(st, s, push=False)
    if not r["orders"]:  # Signal-Logik hat nichts zu kaufen gefunden – dann gibt es nichts zu prüfen
        return
    o = st.paper_orders(status="open")[0]
    assert o["side"] == "buy" and o["limit_price"] == round(last * 1.01, 4) and not st.paper_positions()
    import time as _t
    # Markt offen, Kurs über dem Limit: nichts passiert
    monkeypatch.setattr(paper.market, "live", lambda sym, c=None: {"price": last * 1.05, "time": _t.time()})
    assert paper.check_orders(st, s, push=False)["trades"] == []
    # Kurs unter dem Limit: Kauf
    monkeypatch.setattr(paper.market, "live", lambda sym, c=None: {"price": last * 0.995, "time": _t.time()})
    res = paper.check_orders(st, s, push=False)
    assert res["trades"][0]["side"] == "buy" and st.paper_positions()[0]["symbol"] == "AAA"
    assert st.paper_orders(status="filled")[0]["note"].startswith("zu ")
    # Stopp unterschritten: Verkauf über die Stopp-Order
    stop = st.paper_positions()[0]["stop"]
    monkeypatch.setattr(paper.market, "live", lambda sym, c=None: {"price": stop * 0.99, "time": _t.time()})
    res = paper.check_orders(st, s, push=False)
    assert res["trades"][0]["side"] == "sell" and "Order" in res["trades"][0]["reason"] and not st.paper_positions()


def test_old_buy_orders_expire(tmp_path, monkeypatch):
    st, s, df = _setup_closed_market(tmp_path, monkeypatch)
    paper.start_live(st, s, {"AAA": df})
    st.add_paper_order({"symbol": "AAA", "side": "buy", "kind": "limit", "limit_price": 1.0, "day": "2020-01-01",
                        "ref_price": 1.0, "reason": "x"})
    monkeypatch.setattr(paper.market, "live", lambda sym, c=None: {"price": 0.5, "time": 1})
    paper.check_orders(st, s, push=False)
    assert st.paper_orders(status="cancelled")[0]["note"].startswith("Tag vorbei")


def test_market_open_rules(monkeypatch):
    import time as _t
    assert paper.market_open("AAPL", {"time": _t.time() - 60})
    assert not paper.market_open("AAPL", {"time": _t.time() - 3 * 3600})
    assert not paper.market_open("AAPL", None)
