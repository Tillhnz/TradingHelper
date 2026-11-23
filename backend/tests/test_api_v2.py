"""API der neuen Bereiche: Portfolio/Import, Markt, Modell, Startseite. Läuft in der CI (FastAPI)."""
import base64
import json

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app import main, market, news  # noqa: E402
from app.config import settings  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch, uptrend):
    settings.reset()
    settings.data_dir = tmp_path
    settings.scheduler_enabled = False
    settings.secret_key = "test-secret"
    settings.require_2fa = False
    settings.social_enabled = False
    main._fails.clear()
    monkeypatch.setattr(market, "get_history", lambda *a, **k: uptrend)
    monkeypatch.setattr(market, "symbol_info", lambda s: {"symbol": s.upper(), "name": "SAP SE", "exchange": "gettex",
                                                           "currency": "EUR", "type": "Aktie"})
    monkeypatch.setattr(news, "fetch_feed", lambda *a, **k: [])
    with TestClient(main.app) as c:
        yield c
    settings.reset()


def _login(c):
    r = c.post("/api/auth/setup", json={"username": "till", "password": "geheim123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_overview_is_fast_and_complete(client):
    h = _login(client)
    client.post("/api/watchlist", json={"symbol": "DE0007164600.GTX"}, headers=h)
    rows = client.get("/api/watchlist/overview", headers=h).json()
    assert rows[0]["symbol"] == "DE0007164600.GTX" and rows[0]["price"] and rows[0]["action"]
    assert not rows[0].get("pending")


def test_import_flow_and_portfolio(client):
    h = _login(client)
    assert client.get("/api/portfolio", headers=h).json()["value"] == 0
    banks = client.get("/api/portfolio/banks", headers=h).json()
    assert any(b["id"] == "consorsbank" for b in banks["banks"]) and all(b["kind"] == "import" for b in banks["banks"])
    aid = client.post("/api/portfolio/accounts", json={"bank": "finanzen_zero"}, headers=h).json()["id"]
    csv = "Datum;Typ;ISIN;Stück;Kurs\n01.02.2026;Kauf;DE0007164600;10;100\n"
    files = [{"name": "umsaetze.csv", "content": base64.b64encode(csv.encode()).decode()}]
    pv = client.post(f"/api/portfolio/accounts/{aid}/import/preview", json={"files": files}, headers=h).json()
    assert len(pv["trades"]) == 1 and not pv["trades"][0]["duplicate"]
    res = client.post(f"/api/portfolio/accounts/{aid}/import", json={"trades": pv["trades"]}, headers=h).json()
    assert res["created"] == 1
    pv2 = client.post(f"/api/portfolio/accounts/{aid}/import/preview", json={"files": files}, headers=h).json()
    assert pv2["trades"][0]["duplicate"] is True
    pf = client.get("/api/portfolio", headers=h).json()
    assert pf["value"] > 0 and pf["lines"][0]["account"] == "finanzen.net zero" and pf["allocation"]["account"]
    cid = client.post("/api/portfolio/accounts", json={"bank": "consorsbank"}, headers=h).json()["id"]
    assert client.patch(f"/api/portfolio/accounts/{cid}", json={"label": "Consors"}, headers=h).status_code == 200
    assert client.post("/api/portfolio/accounts", json={"bank": "gibtsnicht"}, headers=h).status_code == 422
    assert client.delete(f"/api/portfolio/accounts/{aid}", headers=h).status_code == 200


def test_insight_endpoints(client):
    h = _login(client)
    assert len(client.get("/api/markets", headers=h).json()["items"]) >= 5
    m = client.get("/api/macro", headers=h).json()
    assert "indicators" in m and "regime" in m
    assert "fear_greed" in client.get("/api/mood", headers=h).json()
    assert client.get("/api/model", headers=h).json()["horizons"] == {}
    assert client.get("/api/model/decisions", headers=h).json() == {"items": []}
    s = client.get("/api/social/AAPL", headers=h).json()
    assert s["enabled"] is False and s["data"] is None
    a = client.get("/api/analysis/AAPL?with_news=false", headers=h).json()
    assert "model" in a  # ohne trainiertes Modell: None
    st = client.get("/api/admin/status", headers=h).json()
    assert "data" in st


def test_home_layout_roundtrip(client):
    h = _login(client)
    layout = {"v": 2, "widgets": [{"id": "a", "type": "markets", "size": "s"},
                                  {"id": "b", "type": "chart", "size": "m", "config": {"symbol": "SAP.DE"}}], "private": True}
    r = client.put("/api/settings", json={"home_layout": json.dumps(layout)}, headers=h)
    assert r.status_code == 200
    saved = json.loads(r.json()["fields"]["home_layout"]["value"])
    assert [w["type"] for w in saved["widgets"]] == ["markets", "chart"] and saved["private"] is True
