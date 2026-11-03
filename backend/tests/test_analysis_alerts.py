import numpy as np
import pytest

from app import alerts, analysis, news
from app.config import Settings
from app.storage import Storage

from conftest import make_df


def test_uptrend_scores_positive(uptrend):
    a = analysis.analyze("TEST", uptrend)
    assert a.normalized > 0
    assert any(s.name == "Trend" and s.score == 2 for s in a.signals)
    assert a.support < a.last_close < a.resistance or a.resistance is not None


def test_downtrend_scores_negative(downtrend):
    a = analysis.analyze("TEST", downtrend)
    assert a.normalized < 0
    rec = analysis.recommend(a, sentiment=-0.8)
    assert rec.combined < a.normalized  # negative News drücken den Score weiter
    assert rec.action != "Kaufen prüfen"
    a.signals = [analysis.Signal("Trend", -2, "x"), analysis.Signal("MACD", -2, "y")]
    assert analysis.recommend(a, sentiment=-0.5).action == "Reduzieren prüfen"


def test_recommend_neutral_band(uptrend):
    a = analysis.analyze("TEST", uptrend)
    a.signals = [analysis.Signal("x", 0, "neutral")]
    assert analysis.recommend(a, None).action == "Halten / beobachten"


def test_too_short_history():
    with pytest.raises(ValueError):
        analysis.analyze("X", make_df(np.arange(10) + 100.0))


def test_sentiment_lexicon():
    assert news.score_text("Apple beats estimates, shares surge to record") > 0.5
    assert news.score_text("Company misses, stock plunges after downgrade") < -0.5
    assert news.score_text("Hauptversammlung am Dienstag") == 0
    assert news.score_text("Gewinnwarnung: Aktie fällt") < 0


def test_build_params():
    assert alerts.build_params("rsi_below", {"value": "25"}) == {"value": 25.0, "period": 14}
    assert alerts.build_params("ma_cross_up", {"type": "EMA"})["type"] == "ema"
    with pytest.raises(ValueError):
        alerts.build_params("price_above", {})
    with pytest.raises(ValueError):
        alerts.build_params("nope", {})


def _alert(st, kind, **params):
    aid = st.add_alert("TEST", kind, alerts.build_params(kind, params))
    return st.get_alert(aid)


def test_alert_evaluation(tmp_path):
    st = Storage(tmp_path / "t.db")
    df = make_df([100.0] * 60 + [110.0])
    assert alerts.evaluate(_alert(st, "cross_up", value=105), df)
    assert alerts.evaluate(_alert(st, "price_above", value=105), df)
    assert not alerts.evaluate(_alert(st, "price_below", value=105), df)
    assert alerts.evaluate(_alert(st, "pct_change", value=5), df)
    assert alerts.evaluate(_alert(st, "new_high", lookback=52), df)
    assert alerts.evaluate(_alert(st, "bb_break"), df)
    assert alerts.evaluate(_alert(st, "price_cross_ma", period=20), df)


def test_golden_cross_alert(tmp_path):
    st = Storage(tmp_path / "t.db")
    closes = np.r_[np.linspace(200, 100, 230), np.linspace(100, 220, 60)]
    df = make_df(closes)
    a = _alert(st, "ma_cross_up", fast=50, slow=200)
    # Finde die Kerze, an der SMA50 die SMA200 kreuzt, und prüfe genau dort
    hits = [i for i in range(201, len(df)) if alerts.evaluate(a, df.iloc[: i + 1])]
    assert len(hits) == 1
    assert "Golden Cross" in alerts.evaluate(a, df.iloc[: hits[0] + 1])


def test_check_all_cooldown_and_once(tmp_path, monkeypatch):
    st = Storage(tmp_path / "t.db")
    df = make_df([100.0] * 60 + [110.0])
    monkeypatch.setattr(alerts.market, "get_history", lambda *a, **k: df)
    monkeypatch.setattr(alerts.market, "symbol_info", lambda s: {"currency": "USD"})
    sent = []
    monkeypatch.setattr(alerts.notify, "send", lambda *a, **k: sent.append(a) or True)
    s = Settings(data_dir=tmp_path, alert_cooldown_minutes=60)

    st.add_alert("TEST", "price_above", {"value": 105})
    st.add_alert("TEST", "price_above", {"value": 105}, once=True)
    assert len(alerts.check_all(st, s)) == 2
    assert len(sent) == 2
    assert alerts.check_all(st, s) == []  # Cooldown bzw. deaktiviert
    assert [a.active for a in st.alerts()] == [True, False]
    assert len(st.alert_log()) == 2


def test_watchlist(tmp_path):
    st = Storage(tmp_path / "t.db")
    st.add_symbol("aapl")
    st.add_symbol("sap.de", "Langfrist")
    assert st.watchlist_symbols() == ["AAPL", "SAP.DE"]
    assert st.remove_symbol("AAPL")
    assert not st.remove_symbol("AAPL")
