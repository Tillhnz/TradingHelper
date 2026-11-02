import numpy as np
import pandas as pd
import pytest


def make_df(closes) -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    idx = pd.date_range("2025-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({
        "open": closes * 0.995, "high": closes * 1.01, "low": closes * 0.99,
        "close": closes, "volume": np.full(len(closes), 1_000_000.0),
    }, index=idx)


@pytest.fixture
def uptrend():
    rng = np.random.default_rng(1)
    return make_df(100 + np.arange(260) * 0.5 + rng.normal(0, 1, 260))


@pytest.fixture
def downtrend():
    rng = np.random.default_rng(2)
    return make_df(250 - np.arange(260) * 0.5 + rng.normal(0, 1, 260))
