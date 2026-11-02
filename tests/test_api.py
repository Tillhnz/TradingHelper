import pytest
from fastapi.testclient import TestClient

from tradehelper import api, market
from tradehelper.config import Settings, get_settings


@pytest.fixture
def client(tmp_path, monkeypatch, uptrend):
    settings = Settings(data_dir=tmp_path, api_key="secret", finnhub_api_key="")
    api.app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(api, "get_settings", lambda: settings)
    monkeypatch.setattr(market, "get_history", lambda *a, **k: uptrend)
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


H = {"X-API-Key": "secret"}


def test_auth(client):
    assert client.get("/health").status_code == 200
    assert client.get("/watchlist").status_code == 401
    assert client.get("/watchlist", headers=H).status_code == 200


def test_watchlist_and_report(client):
    assert client.post("/watchlist", json={"symbol": "aapl"}, headers=H).status_code == 201
    assert client.get("/watchlist", headers=H).json()[0]["symbol"] == "AAPL"
    rep = client.get("/report", headers=H).json()
    assert rep["entries"][0]["symbol"] == "AAPL"
    assert rep["entries"][0]["action"] in {"Kaufen prüfen", "Halten / beobachten", "Reduzieren prüfen"}


def test_analysis_and_history(client):
    a = client.get("/analysis/AAPL", headers=H).json()
    assert "recommendation" in a and a["metrics"]["rsi"] is not None
    h = client.get("/history/AAPL", headers=H).json()
    assert len(h["rows"]) == 260 and "sma200" in h["rows"][-1]


def test_alerts_crud(client):
    r = client.post("/alerts", json={"symbol": "AAPL", "kind": "rsi_below", "params": {"value": 30}}, headers=H)
    assert r.status_code == 201
    aid = r.json()["id"]
    assert client.post("/alerts", json={"symbol": "AAPL", "kind": "bad"}, headers=H).status_code == 422
    assert client.post("/alerts/check?send=false", headers=H).status_code == 200
    assert client.delete(f"/alerts/{aid}", headers=H).status_code == 200


def test_chart_page(client):
    html = client.get("/chart/msft").text
    assert "MSFT" in html and "lightweight-charts" in html
