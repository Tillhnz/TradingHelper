import numpy as np
import pandas as pd

from app import analysis, breakout
from app import indicators as ind


def _df(drift, n=600, seed=3):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(drift, 0.015, n)))
    idx = pd.date_range("2023-01-02", periods=n, freq="B")
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e6}, index=idx)


def test_probabilities_follow_the_trend():
    up = breakout.probabilities(ind.add_all(_df(0.003)))
    down = breakout.probabilities(ind.add_all(_df(-0.003)))
    assert up["up"] > up["down"] and up["tilt"] == "up"
    assert down["down"] > down["up"] and down["tilt"] == "down"
    for p in (up, down):
        assert 0 <= p["up"] <= 1 and 0 <= p["down"] <= 1 and p["level_up"] > p["level_down"]


def test_too_short_history_gives_none():
    assert breakout.probabilities(ind.add_all(_df(0, n=100))) is None


def test_likely_breakdown_can_flip_the_opinion():
    a = analysis.analyze("X", _df(-0.003))
    assert a.breakout and a.breakout["tilt"] == "down"
    rec = analysis.recommend(a, None)
    assert any("Rutsch-Risiko" in n for n in rec.notes)
    plain = analysis.analyze("X", _df(-0.003), with_breakout=False)
    assert plain.breakout is None
    assert rec.combined < analysis.recommend(plain, None).combined


def test_tilt_respects_what_is_usual():
    assert breakout.tilt(0.42, 0.30, 0.60, 0.14) == "neutral"  # oben vorn, aber unter dem Üblichen: keine Chance
    assert breakout.tilt(0.30, 0.34, 0.60, 0.14) == "down"
    assert breakout.tilt(0.45, 0.10, 0.30, 0.15) == "up"
    assert breakout.tilt(0.25, 0.22, 0.25, 0.22) == "neutral"


def test_news_shift_probabilities():
    bo = {"up": 0.3, "down": 0.3, "base_up": 0.3, "base_down": 0.3, "tilt": "neutral", "edge": 0.0, "days": 10}
    good = breakout.with_news(bo, 0.8, count=6)
    bad = breakout.with_news(bo, -0.8, count=6)
    assert good["up"] > 0.3 > good["down"] and good["tilt"] == "up"
    assert bad["down"] > 0.3 > bad["up"] and bad["tilt"] == "down"
    assert good["news"]["up_before"] == 0.3
    few = breakout.with_news(bo, 0.8, count=1)
    assert few["up"] < good["up"]  # wenige Meldungen zählen weniger
    assert breakout.with_news(bo, None) is bo and breakout.with_news(None, 0.5) is None


def test_recommend_applies_news_once():
    a = analysis.analyze("X", _df(0.0))
    before = dict(a.breakout)
    analysis.recommend(a, 0.9, news_count=8)
    assert a.breakout["news"]["sentiment"] == 0.9 and a.breakout["up"] >= before["up"]
    analysis.recommend(a, 0.9, news_count=8)  # nicht doppelt anwenden
    assert a.breakout["news"]["up_before"] == before["up"]
