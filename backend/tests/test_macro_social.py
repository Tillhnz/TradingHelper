from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app import macro, marketstore, social


def test_parse_ecb_csv():
    text = ("KEY,FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE,OBS_STATUS\n"
            "FM.D.U2.EUR.4F.KR.DFR.LEV,D,U2,2026-10-29,2.0,A\n"
            "FM.D.U2.EUR.4F.KR.DFR.LEV,D,U2,2026-10-30,2.0,A\n"
            "ICP.M.U2.N.000000.4.ANR,M,U2,2026-09,2.2,A\n")
    pts = macro.parse_ecb_csv(text)
    assert pts[0] == ("2026-09-30", 2.2) and pts[-1] == ("2026-10-30", 2.0)


def test_parse_eurostat_jsonstat():
    js = {"id": ["freq", "unit", "geo", "time"], "size": [1, 1, 1, 3],
          "dimension": {"time": {"category": {"index": {"2026-07": 0, "2026-08": 1, "2026-09": 2}}}},
          "value": {"0": 6.3, "2": 6.1}}
    assert macro.parse_eurostat(js) == [("2026-07-31", 6.3), ("2026-09-30", 6.1)]
    q = {"id": ["time"], "size": [2], "dimension": {"time": {"category": {"index": {"2026-Q1": 0, "2026-Q2": 1}}}},
         "value": {"0": 0.2, "1": -0.1}}
    assert macro.parse_eurostat(q) == [("2026-03-31", 0.2), ("2026-06-30", -0.1)]


def test_parse_fred_yoy_and_missing():
    rows = ["observation_date,CPIAUCSL"] + [f"{2025 + (m // 12)}-{m % 12 + 1:02d}-01,{100 + m}" for m in range(14)]
    rows.append("2026-03-01,.")
    pts = macro.parse_fred_csv("\n".join(rows), yoy=True)
    assert len(pts) == 2 and pts[0] == ("2026-01-01", 12.0)
    assert macro.parse_fred_csv("DATE,UNRATE\n2026-09-01,4.3\n") == [("2026-09-01", 4.3)]


def test_parse_worldbank():
    js = [{"page": 1}, [{"date": "2025", "value": 2.61}, {"date": "2024", "value": None}, {"date": "2023", "value": 2.7}]]
    assert macro.parse_worldbank(js) == [("2023-12-31", 2.7), ("2025-12-31", 2.61)]


def test_sector_mapping():
    assert macro.sector_etf("Technologie", "Software") == "XLK"
    assert macro.sector_etf("Financial Services", "Banks—Regional") == "XLF"
    assert macro.sector_etf("Healthcare") == "XLV"
    assert macro.sector_etf(None) is None


@pytest.fixture
def store(tmp_path):
    st = marketstore.open_store(tmp_path / "m.db")
    yield st
    marketstore.close_store()


def test_indicators_and_point_in_time(store):
    store.put("macro:ea_inflation", {"points": [["2026-06-30", 2.6], ["2026-07-31", 2.4], ["2026-08-31", 2.3],
                                                ["2026-09-30", 2.1]]})
    store.put("macro:ea_sentiment", {"points": [["2026-06-30", 95.0], ["2026-09-30", 97.0]]})
    ind = {i["id"]: i for i in macro.indicators()}
    assert ind["ea_inflation"]["value"] == 2.1 and ind["ea_inflation"]["change"] < 0
    assert ind["ea_inflation"]["tone"] == 1  # sinkende Inflation = gut für Aktien
    reg = macro.regime()
    assert reg and reg["growth_up"] and not reg["inflation_up"]
    days = pd.date_range("2026-09-01", "2026-11-10", freq="D")
    f = macro.asof_frame(days, ["ea_inflation"])
    # September-Zahl (Stichtag 30.9.) ist erst nach 20 Tagen Verzögerung bekannt
    assert f.loc["2026-10-15", "ea_inflation"] == 2.3
    assert f.loc["2026-10-25", "ea_inflation"] == 2.1


def test_social_scoring_and_ticker():
    now = datetime.now(timezone.utc)
    posts = [{"text": "Great earnings beat, strong buy", "label": 1, "time": now.isoformat(), "likes": 10},
             {"text": "Aktie stürzt ab nach Gewinnwarnung", "label": 0, "time": (now - timedelta(days=3)).isoformat()},
             {"text": "bullish", "label": 1, "time": (now - timedelta(hours=2)).isoformat()}]
    s = social.score_posts(posts)
    assert s["n"] == 3 and s["score"] > 0 and s["bull"] == 2 and s["bear"] == 1 and s["last24"] == 2
    assert social._ticker_for("AAPL", None) == "AAPL"
    assert social._ticker_for("BTC-EUR", None) == "BTC.X"
    assert social._ticker_for("US0378331005.GTX", {"ticker": "AAPL"}) == "AAPL"
    assert social._ticker_for("^GDAXI", None) is None and social._ticker_for("SAP.DE", None) is None
