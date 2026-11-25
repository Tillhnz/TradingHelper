import numpy as np
import pandas as pd
import pytest

from app import drivers, market, news


def _df(close, idx):
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1}, index=idx)


@pytest.fixture
def world(monkeypatch):
    rng = np.random.default_rng(7)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=260)
    m = rng.normal(0.0004, 0.01, len(idx))          # Markt
    x = rng.normal(0.0, 0.008, len(idx))            # Branche über den Markt hinaus
    e = rng.normal(0.0, 0.006, len(idx))            # Eigenes
    e[-15] = -0.12                                  # ein eigener Absturztag vor 3 Wochen
    stock = 100 * np.exp(np.cumsum(1.2 * m + 0.8 * x + e))
    index = 1000 * np.exp(np.cumsum(m))
    sector = 50 * np.exp(np.cumsum(m + x))
    data = {"TEST.DE": _df(stock, idx), "^GDAXI": _df(index, idx), "XLK": _df(sector, idx)}

    def hist(sym, period="1y", interval="1d", currency=None):
        if sym not in data:
            raise market.MarketDataError("fehlt")
        return data[sym]

    monkeypatch.setattr(market, "get_history", hist)
    monkeypatch.setattr(market, "cached_info", lambda s: {"name": "Testwerk AG", "isin": "DE0001234567", "currency": "EUR"})
    from app import brain

    monkeypatch.setattr(brain, "sector_of", lambda s: "XLK")
    monkeypatch.setattr(drivers, "headlines_on", lambda term, day, limit=3: [{"headline": f"{term} senkt Prognose", "url": "", "source": "x", "published": day, "sentiment": -0.6}])
    monkeypatch.setattr(news, "cached_sentiment", lambda s: (-0.4, 5))
    return data, idx


def test_explains_market_sector_and_own(world):
    _, idx = world
    r = drivers.compute("TEST.DE")
    assert r["market"]["label"] == "DAX" and r["sector"]["symbol"] == "XLK"
    # die Regression findet die eingebauten Empfindlichkeiten wieder
    assert r["fit"]["beta_m"] == pytest.approx(1.2, abs=0.25)
    assert r["fit"]["beta_x"] == pytest.approx(0.8, abs=0.3)
    month = next(w for w in r["windows"] if w["label"] == "Monat")
    # die Anteile ergeben zusammen die Gesamtänderung
    assert month["market"] + month["sector"] + month["own"] == pytest.approx(month["total"], abs=0.2)
    # der eigene Absturztag wird gefunden und mit Schlagzeile versehen
    assert r["big_days"] and r["big_days"][0]["pct"] < -8
    assert r["big_days"][0]["news"][0]["headline"].startswith("Testwerk")
    text = " ".join(r["summary"])
    assert "Davon der Markt" in text and "Nachrichtenlage: negativ" in text


def test_country_from_isin_and_suffix():
    assert drivers.country_of("NL0000235190.GTX", {}) == "NL"
    assert drivers.country_of("AAPL", {"country": "United States"}) == "US"
    assert drivers.country_of("SAP.DE", {}) == "DE"


def test_too_little_data(monkeypatch):
    monkeypatch.setattr(market, "get_history", lambda *a, **k: _df(np.ones(5), pd.bdate_range("2026-01-01", periods=5)))
    monkeypatch.setattr(market, "cached_info", lambda s: {})
    assert drivers.compute("NEW.DE")["empty"] is True
