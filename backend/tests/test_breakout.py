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
    assert any("Rutsch unter" in n for n in rec.notes)
    plain = analysis.analyze("X", _df(-0.003), with_breakout=False)
    assert plain.breakout is None
    assert rec.combined < analysis.recommend(plain, None).combined
