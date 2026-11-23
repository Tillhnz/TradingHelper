import numpy as np
import pandas as pd
import pytest

from app import analysis, brain, marketstore
from app.storage import Storage


def _series(seed: int, n: int = 1100) -> pd.DataFrame:
    """Zufallspfad mit einem lernbaren Muster: nach starken Rückgängen über 20 Tage folgt oft eine Erholung."""
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0003, 0.015, n)
    price = [100.0]
    for i in range(1, n):
        past = np.log(price[-1] / price[max(0, i - 20)]) if i > 20 else 0
        drift = 0.008 if past < -0.06 else (-0.006 if past > 0.08 else 0)
        price.append(price[-1] * float(np.exp(r[i] + drift)))
    c = np.array(price)
    idx = pd.bdate_range("2022-01-03", periods=n)
    return pd.DataFrame({"open": c * (1 + rng.normal(0, 0.002, n)), "high": c * 1.01, "low": c * 0.99, "close": c,
                         "volume": rng.integers(1e5, 1e6, n).astype(float)}, index=idx)


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app.config import settings

    settings.reset()
    settings.data_dir = tmp_path
    st = marketstore.open_store(tmp_path / "market.db")
    brain._MODELS.clear()
    yield st
    marketstore.close_store()
    settings.reset()


def test_features_and_labels_shapes():
    df = _series(1, 400)
    f = brain.tech_features(df)
    assert set(brain.TECH) <= set(f.columns)
    assert f["rsi"].dropna().between(0, 1).all()
    fwd, cls = brain.labels(df["close"], f["vol_20"], 20)
    assert cls.iloc[-20:].isna().all() and cls.dropna().isin([0, 1, 2]).all()
    assert abs(fwd.iloc[30] - (df["close"].iloc[50] / df["close"].iloc[30] - 1)) < 1e-12


def test_train_walk_forward_predict_and_journal(env, tmp_path, monkeypatch):
    monkeypatch.setattr(brain, "CONFIGS", {k: brain.CONFIGS[k] for k in ("ausgewogen", "nur Kurse")})
    monkeypatch.setattr(brain, "FOLDS", 2)
    frames = {f"SYM{i}": _series(i, 1000) for i in range(8)}
    meta = brain.train(None, "medium", list(frames), frames=frames)
    assert meta["rows"] > 4000 and meta["config"] in brain.CONFIGS
    assert meta["folds"] and all("gain" in f for f in meta["folds"])
    assert set(meta["candidates"]) == {"ausgewogen", "nur Kurse"}
    assert 0 <= meta["skill"] <= 1
    # das Muster (Erholung nach Rückgang) ist lernbar → das Modell schlägt die Basisrate
    assert meta["summary"]["gain"] > 0
    pred = brain.predict("SYM0", "medium", df=frames["SYM0"])
    assert pred and abs(pred["p_up"] + pred["p_flat"] + pred["p_down"] - 1) < 1e-6
    assert pred["action"] in (analysis.BUY, analysis.HOLD, analysis.SELL)
    assert pred["drivers"] and pred["drivers"][0]["group"] == "Technik"

    # Kombination: Modell darf bremsen/verkaufen, aber keinen Kauf allein auslösen
    prof = analysis.Profile("medium", "balanced")
    sell = brain.combine(0.0, analysis.HOLD, {"expected": -0.9}, 0.6, prof)
    assert sell["action"] == analysis.SELL
    buy = brain.combine(0.1, analysis.HOLD, {"expected": 0.9}, 0.6, prof)
    assert buy["action"] == analysis.HOLD
    assert brain.combine(0.5, analysis.BUY, None, 0.6, prof) == {"action": analysis.BUY, "score": 0.5, "weight": 0.0}


def test_journal_verdicts(tmp_path, monkeypatch):
    st = Storage(tmp_path / "x.db")
    df = _series(3, 300)
    monkeypatch.setattr(brain, "_history", lambda s: df)
    day = str(df.index[100].date())
    st.save_decision({"symbol": "X", "day": day, "horizon": "medium", "price": float(df["close"].iloc[100]),
                      "rule_action": analysis.HOLD, "model_action": analysis.SELL, "final_action": analysis.HOLD,
                      "features": {"drivers": [{"group": "Technik", "text": "Kursverlauf", "delta": 0.2}]}})
    assert brain.evaluate_journal(st) == 1
    d = st.decisions(evaluated=True)[0]
    fwd = df["close"].iloc[120] / df["close"].iloc[100] - 1
    assert abs(d["outcome"] - fwd) < 1e-4
    assert d["verdict"]
    if d["outcome_label"] == "down":
        assert d["verdict"].startswith("Verkaufen wäre besser")
        assert "Modell lag richtig" in d["lesson"]
    tr = brain.track_record("medium", days=100000, storage=st)
    assert tr["n"] == 1


@pytest.mark.parametrize("final,cls,expect,ok", [
    (analysis.SELL, 2, "Halten wäre besser", False), (analysis.HOLD, 0, "Verkaufen wäre besser", False),
    (analysis.SELL, 0, "Richtig: Verkaufen", True), (analysis.BUY, 2, "Richtig: Kauf", True),
    (analysis.HOLD, 2, "Richtig gehalten", True)])
def test_verdict_texts(final, cls, expect, ok):
    text, good = brain._verdict(final, cls, 0.05 if cls == 2 else -0.05, 20)
    assert text.startswith(expect) and good is ok
