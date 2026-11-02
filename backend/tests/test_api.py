import pytest
from fastapi.testclient import TestClient

from app import main, market
from app.config import settings


@pytest.fixture
def client(tmp_path, monkeypatch, uptrend):
    settings.reset()
    settings.data_dir = tmp_path
    settings.scheduler_enabled = False
    settings.updater_url = ""
    settings.secret_key = "test-secret"
    main._fails.clear()
    monkeypatch.setattr(market, "get_history", lambda *a, **k: uptrend)
    with TestClient(main.app) as c:
        yield c
    settings.reset()


def _login(client) -> dict:
    r = client.post("/api/auth/setup", json={"username": "till", "password": "geheim123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_setup_login_flow(client):
    assert client.get("/api/auth/status").json() == {"setup_required": True}
    assert client.get("/api/watchlist").status_code == 401
    h = _login(client)
    assert client.get("/api/auth/status").json() == {"setup_required": False}
    assert client.post("/api/auth/setup", json={"username": "x", "password": "geheim123"}).status_code == 409
    assert client.get("/api/me", headers=h).json()["username"] == "till"
    assert client.post("/api/auth/login", json={"username": "till", "password": "falsch"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "Till", "password": "geheim123"}).status_code == 200


def test_password_change_invalidates_old_token(client):
    h = _login(client)
    r = client.post("/api/auth/password", json={"current": "geheim123", "new": "neuesPasswort1"}, headers=h)
    assert r.status_code == 200
    assert client.get("/api/me", headers=h).status_code == 401
    assert client.get("/api/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).status_code == 200


def test_login_rate_limit(client):
    _login(client)
    for _ in range(8):
        client.post("/api/auth/login", json={"username": "till", "password": "falsch"})
    assert client.post("/api/auth/login", json={"username": "till", "password": "geheim123"}).status_code == 429


def test_watchlist_overview_and_report(client):
    h = _login(client)
    assert client.post("/api/watchlist", json={"symbol": "aapl"}, headers=h).status_code == 201
    ov = client.get("/api/watchlist/overview", headers=h).json()
    assert ov[0]["symbol"] == "AAPL" and len(ov[0]["spark"]) == 30 and ov[0]["action"]
    rep = client.get("/api/report", headers=h).json()
    assert rep["entries"][0]["symbol"] == "AAPL"
    assert client.post("/api/report/send", headers=h).status_code == 400  # kein Topic


def test_history_and_analysis(client):
    h = _login(client)
    rows = client.get("/api/history/AAPL", headers=h).json()["rows"]
    assert len(rows) == 260 and rows[-1]["sma200"] is not None and isinstance(rows[-1]["time"], int)
    a = client.get("/api/analysis/AAPL", headers=h).json()
    assert a["recommendation"]["action"] and a["metrics"]["rsi"] is not None


def test_alerts_crud(client):
    h = _login(client)
    kinds = client.get("/api/alerts/kinds", headers=h).json()
    assert any(k["name"] == "rsi_below" for k in kinds["kinds"])
    r = client.post("/api/alerts", json={"symbol": "AAPL", "kind": "rsi_below", "params": {"value": 30}}, headers=h)
    assert r.status_code == 201
    aid = r.json()["id"]
    assert client.patch(f"/api/alerts/{aid}", json={"active": False}, headers=h).json()["active"] is False
    assert client.post("/api/alerts", json={"symbol": "AAPL", "kind": "bad"}, headers=h).status_code == 422
    assert client.post("/api/alerts", json={"symbol": "AAPL", "kind": "macd_cross_up", "interval": "3m"},
                       headers=h).status_code == 422
    assert client.post("/api/alerts/check?send=false", headers=h).status_code == 200
    assert client.delete(f"/api/alerts/{aid}", headers=h).status_code == 200


def test_settings_roundtrip(client):
    h = _login(client)
    r = client.put("/api/settings", json={"ntfy_topic": "th-test", "finnhub_api_key": "k", "report_time": "06:30"},
                   headers=h)
    assert r.status_code == 200
    f = r.json()["fields"]
    assert f["ntfy_topic"]["value"] == "th-test" and f["finnhub_api_key"]["set"] is True
    assert "value" not in f["finnhub_api_key"]
    assert client.put("/api/settings", json={"report_time": "nope"}, headers=h).status_code == 422


def test_admin_without_updater(client):
    h = _login(client)
    st = client.get("/api/admin/status", headers=h).json()
    assert any(c["label"] == "Update-Dienst" and not c["ok"] for c in st["checks"])
    assert client.get("/api/admin/update", headers=h).status_code == 503
    assert client.get("/api/version", headers=h).json()["version"]
