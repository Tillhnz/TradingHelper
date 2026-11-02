import numpy as np
import pandas as pd

from tradehelper import indicators as ind

from conftest import make_df


def test_sma_ema():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    assert ind.sma(s, 3).tolist()[2:] == [2.0, 3.0, 4.0]
    assert np.isnan(ind.ema(s, 3).iloc[1])
    assert ind.ema(s, 3).iloc[-1] > ind.sma(s, 3).iloc[-1] - 1


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 50, dtype=float))
    down = pd.Series(np.arange(50, 1, -1, dtype=float))
    assert ind.rsi(up).iloc[-1] == 100
    assert ind.rsi(down).iloc[-1] < 1
    rng = np.random.default_rng(0)
    r = ind.rsi(pd.Series(100 + rng.normal(0, 1, 300).cumsum())).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_rsi_matches_reference():
    # Referenzwert nach Wilder (klassisches Beispiel aus "New Concepts in Technical Trading Systems")
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03,
              45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64]
    r = ind.rsi(pd.Series(closes), 14)
    assert np.isnan(r.iloc[13])
    assert abs(r.iloc[14] - 70.53) < 0.1
    assert abs(r.iloc[15] - 66.32) < 0.1


def test_macd_and_bollinger_shapes(uptrend):
    m = ind.macd(uptrend["close"])
    assert list(m.columns) == ["macd", "signal", "hist"]
    assert m["macd"].iloc[-1] > 0  # Aufwärtstrend
    b = ind.bollinger(uptrend["close"])
    last = b.iloc[-1]
    assert last.bb_lower < last.bb_mid < last.bb_upper


def test_crossing_helpers():
    a = pd.Series([1.0, 2.0, 4.0])
    assert ind.crossed_above(a, 3.0)
    assert not ind.crossed_below(a, 3.0)
    assert ind.crossed_below(pd.Series([5.0, 4.0, 2.0]), 3.0)
    assert not ind.crossed_above(pd.Series([np.nan, 4.0]), 3.0)


def test_add_all_columns(uptrend):
    d = ind.add_all(uptrend)
    for col in ["sma200", "rsi", "macd", "bb_upper", "stoch_k", "adx", "atr", "obv"]:
        assert col in d.columns
        assert not np.isnan(d[col].iloc[-1])


def test_atr_positive():
    df = make_df(np.linspace(100, 120, 50))
    assert (ind.atr(df).dropna() > 0).all()
