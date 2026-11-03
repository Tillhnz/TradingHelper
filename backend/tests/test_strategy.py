import pytest

from app import analysis
from app.analysis import BUY, HOLD, SELL, Analysis, Profile, Signal
from app.config import Settings


def _analysis(close=100.0, sma200=90.0, atr=2.0, resistance=120.0, signals=None, profile=None):
    m = {"sma200": sma200, "atr": atr, "atr_pct": atr / close * 100}
    sig = signals if signals is not None else [Signal("Trend", 2, "t"), Signal("MACD", 2, "m"), Signal("RSI", 1, "r")]
    return Analysis("X", close, 0.5, m, sig, support=95.0, resistance=resistance, profile=profile or Profile())


def test_horizon_changes_signal_set(uptrend):
    short = analysis.analyze("X", uptrend, Profile("short"))
    long = analysis.analyze("X", uptrend, Profile("long"))
    names_s = {s.name for s in short.signals}
    names_l = {s.name for s in long.signals}
    assert "EMA 9/21" in names_s and "Momentum" not in names_s
    assert "Momentum" in names_l and not names_l & {"Stochastik", "Bollinger", "Volumen", "EMA 9/21"}
    trend_l = next(s for s in long.signals if s.name == "Trend")
    assert trend_l.weight == 2.0
    assert long.normalized > 0 and short.normalized > 0


def test_thresholds_by_risk():
    sig = [Signal("Trend", 1, "t"), Signal("MACD", 0, "m")]  # normiert 0,25
    assert analysis.recommend(_analysis(signals=sig, profile=Profile(risk="aggressive")), None).action == BUY
    assert analysis.recommend(_analysis(signals=sig, profile=Profile(risk="balanced")), None).action == HOLD
    weak = [Signal("Trend", -1, "t"), Signal("MACD", 0, "m")]  # −0,25
    assert analysis.recommend(_analysis(signals=weak, profile=Profile(risk="conservative")), None).action == SELL
    assert analysis.recommend(_analysis(signals=weak, profile=Profile(risk="aggressive")), None).action == HOLD


def test_conservative_never_buys_below_sma200():
    a = _analysis(sma200=110.0, profile=Profile(risk="conservative"))
    rec = analysis.recommend(a, None)
    assert rec.action == HOLD and any("200-Tage-Linie" in n for n in rec.notes)
    assert analysis.recommend(_analysis(sma200=110.0, profile=Profile(risk="aggressive")), None).action == BUY


def test_crv_gate():
    # Stopp mittelfristig 2,5 × ATR = 95, Widerstand 106 → CRV 1,2
    for risk, expected in [("conservative", HOLD), ("balanced", HOLD), ("aggressive", BUY)]:
        rec = analysis.recommend(_analysis(resistance=106.0, profile=Profile(risk=risk)), None)
        assert rec.stop == 95.0 and rec.target == 106.0 and rec.crv == 1.2
        assert rec.action == expected, risk
    # langfristig: kein Kursziel, kein CRV-Filter, weiter Stopp
    rec = analysis.recommend(_analysis(resistance=106.0, profile=Profile("long", "balanced")), None)
    assert rec.action == BUY and rec.target is None and rec.crv is None and rec.stop == 93.0


def test_volatility_penalty():
    sig = [Signal("Trend", 2, "t"), Signal("MACD", 1, "m")]  # 0,75
    calm = analysis.recommend(_analysis(atr=2.0, signals=sig, profile=Profile(risk="conservative")), None)
    wild = analysis.recommend(_analysis(atr=5.0, signals=sig, profile=Profile(risk="conservative")), None)
    assert calm.combined == 0.75 and wild.combined == 0.6
    assert any("Schwankung" in n for n in wild.notes)
    assert analysis.recommend(_analysis(atr=5.0, signals=sig, profile=Profile(risk="aggressive")), None).combined == 0.75


def test_news_weight_by_horizon():
    sig = [Signal("Trend", 2, "t")]  # Technik +1
    short = analysis.recommend(_analysis(signals=sig, profile=Profile("short", "aggressive")), -1.0)
    long = analysis.recommend(_analysis(signals=sig, profile=Profile("long", "aggressive")), -1.0)
    assert short.combined == pytest.approx(0.2)  # 0,6 − 0,4
    assert long.combined == pytest.approx(0.7)  # 0,85 − 0,15


def test_position_size():
    p = Profile("medium", "balanced", portfolio_size=10_000)
    rec = analysis.recommend(_analysis(profile=p), None)
    # Risiko 1 % = 100 € bei 5 € Abstand → 20 Stück = 2.000 €, begrenzt auf 10 % = 1.000 € → 10 Stück
    assert rec.action == BUY and rec.position["shares"] == 10 and rec.position["value"] == 1000.0
    assert analysis.recommend(_analysis(profile=Profile()), None).position is None


def test_profile_from_settings(tmp_path):
    s = Settings(data_dir=tmp_path)
    s.invest_horizon, s.risk_profile, s.portfolio_size = "long", "conservative", 5000
    p = analysis.profile_from(s)
    assert p.label == "Langfristig · Konservativ" and p.period == "2y" and p.portfolio_size == 5000
