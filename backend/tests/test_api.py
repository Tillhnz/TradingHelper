import pytest
from fastapi.testclient import TestClient

from app import main, market, news
from app.config import settings


def _fake_feed(url, via="", split_source=False):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    if "news.google.com" in url:
        return [news.NewsItem("Apple beats estimates", "", "Reuters", "https://r/1", now, 1.0, via),
                news.NewsItem("Fußball-Ergebnisse", "", "kicker", "https://k/1", now, 0.0, via)]
    if "yahoo" in url:
        return [news.NewsItem("Apple Beats Estimates!", "Mehr Text", "Yahoo", "https://y/1", now, 1.0, via)]
    return [news.NewsItem(f"Marktbericht {via}", "", via, f"https://m/{via}", now, 0.0, via)]


@pytest.fixture
def client(tmp_path, monkeypatch, uptrend):
    settings.reset()
    settings.data_dir = tmp_path
    settings.scheduler_enabled = False
    settings.updater_url = ""
    settings.secret_key = "test-secret"
    main._fails.clear()
    monkeypatch.setattr(market, "get_history", lambda *a, **k: uptrend)
    monkeypatch.setattr(market, "symbol_info", lambda s: {
        "symbol": s.upper(), "name": "Apple Inc.", "exchange": "NasdaqGS", "currency": "USD", "type": "EQUITY"})
    monkeypatch.setattr(news, "fetch_feed", _fake_feed)
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
    assert ov[0]["exchange"] == "NasdaqGS" and ov[0]["native_currency"] == "USD" and ov[0]["currency"] == "EUR"
    rep = client.get("/api/report", headers=h).json()
    assert rep["entries"][0]["symbol"] == "AAPL" and rep["entries"][0]["currency"] == "EUR"
    assert rep["profile"] == "Mittelfristig · Ausgewogen" and "stop" in rep["entries"][0]
    client.put("/api/settings", json={"invest_horizon": "long", "risk_profile": "conservative"}, headers=h)
    assert client.get("/api/report", headers=h).json()["profile"] == "Langfristig · Konservativ"
    assert client.post("/api/report/send", headers=h).status_code == 400  # kein Topic


def test_history_and_analysis(client):
    h = _login(client)
    rows = client.get("/api/history/AAPL", headers=h).json()["rows"]
    assert len(rows) == 260 and rows[-1]["sma200"] is not None and isinstance(rows[-1]["time"], int)
    a = client.get("/api/analysis/AAPL", headers=h).json()
    assert a["recommendation"]["action"] and a["metrics"]["rsi"] is not None
    assert a["currency"] == "EUR" and a["native_currency"] == "USD"
    assert a["entry"]["summary"] and isinstance(a["entry"]["setups"], list)
    assert client.get("/api/history/AAPL?currency=native", headers=h).json()["currency"] == "USD"
    assert client.get("/api/history/AAPL?currency=XYZ", headers=h).status_code == 422


def test_alerts_crud(client):
    h = _login(client)
    kinds = client.get("/api/alerts/kinds", headers=h).json()
    assert any(k["name"] == "rsi_below" for k in kinds["kinds"])
    r = client.post("/api/alerts", json={"symbol": "AAPL", "kind": "rsi_below", "params": {"value": 30}}, headers=h)
    assert r.status_code == 201
    aid = r.json()["id"]
    assert client.patch(f"/api/alerts/{aid}", json={"active": False}, headers=h).json()["active"] is False
    r = client.post("/api/alerts", json={"symbol": "AAPL", "kind": "price_above", "params": {"value": 200},
                                         "currency": "EUR"}, headers=h)
    assert r.json()["currency"] == "EUR"
    assert client.post("/api/alerts", json={"symbol": "AAPL", "kind": "price_above", "params": {"value": 1},
                                            "currency": "XYZ"}, headers=h).status_code == 422
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


def test_search(client, monkeypatch):
    h = _login(client)
    monkeypatch.setattr(market, "search", lambda q: [{"symbol": "APC.DE", "name": "Apple", "exchange": "XETRA",
                                                      "type": "Aktie", "currency": "EUR"}])
    assert client.get("/api/search?q=apple", headers=h).json()[0]["symbol"] == "APC.DE"


def test_positions_crud_and_chart(client, monkeypatch):
    import datetime as dt
    h = _login(client)
    monkeypatch.setattr(market, "convert_price", lambda v, frm, to, day=None: None if v is None else v * 0.5)
    today = dt.date.today()
    bad = client.post("/api/positions", json={"symbol": "AAPL", "quantity": 1, "buy_price": 100, "buy_date": today.isoformat(),
                                              "stop": 120}, headers=h)
    assert bad.status_code == 422
    future = (today + dt.timedelta(days=3)).isoformat()
    assert client.post("/api/positions", json={"symbol": "AAPL", "quantity": 1, "buy_price": 100,
                                                "buy_date": future}, headers=h).status_code == 422
    r = client.post("/api/positions", json={"symbol": "aapl", "quantity": 5, "buy_price": 150, "buy_date": "2025-06-02",
                                             "fees": 1, "currency": "EUR", "stop": 140, "target": 200,
                                             "create_alerts": True}, headers=h)
    assert r.status_code == 201 and r.json()["symbol"] == "AAPL" and len(r.json()["alerts"]) == 2
    pid = r.json()["id"]
    lst = client.get("/api/positions", headers=h).json()
    assert lst["items"][0]["value"] is not None and lst["totals"]["currency"] == "EUR"
    hist = client.get("/api/history/AAPL?currency=native", headers=h).json()
    assert hist["positions"][0]["buy_price"] == 75.0 and hist["positions"][0]["converted"] is True  # EUR → USD (Mock ×0,5)
    assert isinstance(hist["events"], list) and "delay_min" in hist and hist["as_of"]
    upd = client.patch(f"/api/positions/{pid}", json={"stop": 160}, headers=h)
    assert upd.json()["stop"] == 160
    assert client.patch(f"/api/positions/{pid}", json={"sell_price": 190}, headers=h).status_code == 422
    sold = client.patch(f"/api/positions/{pid}", json={"sell_price": 190, "sell_date": today.isoformat()}, headers=h)
    assert sold.json()["sell_price"] == 190
    assert client.get("/api/positions", headers=h).json()["items"][0]["closed"] is True
    assert client.patch(f"/api/positions/{pid}", json={"reopen": True}, headers=h).json()["sell_date"] is None
    assert client.get("/api/positions/history", headers=h).status_code == 200
    assert client.delete(f"/api/positions/{pid}", headers=h).status_code == 200


def test_holding_joins_watchlist(client):
    h = _login(client)
    assert client.post("/api/positions", json={"symbol": "MSFT", "quantity": 3, "buy_price": 100,
                                               "buy_date": "2025-06-02", "stop": 90}, headers=h).status_code == 201
    assert "MSFT" in [w["symbol"] for w in client.get("/api/watchlist", headers=h).json()]
    ov = client.get("/api/watchlist/overview", headers=h).json()
    row = next(r for r in ov if r["symbol"] == "MSFT")
    assert row["holding"]["shares"] == 3 and row["holding"]["advice"]["text"]
    assert client.delete("/api/watchlist/MSFT", headers=h).status_code == 409
    hold = client.get("/api/holdings/MSFT", headers=h).json()
    assert hold["summary"]["shares"] == 3 and len(hold["items"]) == 1
    rep = client.get("/api/report", headers=h).json()
    assert next(e for e in rep["entries"] if e["symbol"] == "MSFT")["holding"]["shares"] == 3
    assert client.get("/api/holdings/NONE", headers=h).json()["summary"] is None


def test_news_endpoints(client):
    h = _login(client)
    client.post("/api/watchlist", json={"symbol": "AAPL"}, headers=h)
    r = client.get("/api/news/AAPL", headers=h).json()
    # Google + Yahoo zusammengeführt, Duplikat entfernt, Fußball nicht relevant
    assert [i["headline"] for i in r["items"]] == ["Apple Beats Estimates!"]
    assert r["sources"] == ["Google News", "Yahoo Finance"]
    w = client.get("/api/news/watchlist", headers=h).json()
    assert w["items"][0]["symbol"] == "AAPL" and w["items"][0]["name"] == "Apple Inc."
    m = client.get("/api/news/market", headers=h).json()
    assert "tagesschau Wirtschaft" in m["feeds"] and len(m["items"]) == len(m["feeds"])
    assert client.put("/api/settings", json={"news_feeds": "Nur eine | https://x.example/rss", "news_yahoo": False},
                      headers=h).status_code == 200
    assert client.get("/api/news/market", headers=h).json()["feeds"] == ["Nur eine"]
    assert client.get("/api/news/AAPL", headers=h).json()["sources"] == ["Google News"]
    assert client.put("/api/settings", json={"news_feeds": "kaputt"}, headers=h).status_code == 422


def test_paper_endpoints(client):
    h = _login(client)
    assert client.post("/api/paper/run", headers=h).status_code == 400  # leere Watchlist
    assert client.get("/api/paper", headers=h).json()["started"] is False
    client.post("/api/watchlist", json={"symbol": "AAPL"}, headers=h)
    r = client.post("/api/paper/run", headers=h)
    assert r.status_code == 200 and r.json()["errors"] == {}
    v = client.get("/api/paper", headers=h).json()
    assert v["started"] and v["capital"] == 10000 and v["enabled"] is True
    assert client.put("/api/settings", json={"paper_fee": "1,5", "paper_capital": 5000}, headers=h).status_code == 200
    assert client.put("/api/settings", json={"paper_fee": "-1"}, headers=h).status_code == 422
    assert client.get("/api/paper/backtest", headers=h).json()["status"] in ("idle", "done", "error", "running")
    assert client.post("/api/paper/reset", headers=h).json() == {"ok": True}
    assert client.get("/api/paper", headers=h).json()["capital"] == 5000


def test_quotes_and_trailing_position(client, monkeypatch):
    h = _login(client)
    monkeypatch.setattr(market, "live", lambda s, c=None: {"symbol": s, "price": 101.5, "currency": "USD", "change_pct": 1.2})
    r = client.get("/api/quotes?symbols=AAPL,msft", headers=h).json()
    assert [q["symbol"] for q in r] == ["AAPL", "MSFT"] and r[0]["price"] == 101.5
    p = client.post("/api/positions", json={"symbol": "AAPL", "quantity": 1, "buy_price": 100, "buy_date": "2026-01-02",
                                            "stop": 90, "target": 150, "trail_pct": 6, "create_alerts": True}, headers=h).json()
    kinds = sorted(client.get("/api/alerts", headers=h).json(), key=lambda a: a["kind"])
    assert [a["kind"] for a in kinds] == ["price_above"]  # kein fester Stopp-Alarm bei mitlaufendem Stopp
    # Ziel ändern verschiebt den passenden Kursalarm mit
    client.patch(f"/api/positions/{p['id']}", json={"target": 160}, headers=h)
    assert client.get("/api/alerts", headers=h).json()[0]["params"]["value"] == 160
    a = client.get("/api/analysis/AAPL", headers=h).json()
    assert a["recommendation"]["trail_pct"] >= 2
    hold = client.get("/api/holdings/AAPL", headers=h).json()["items"][0]
    assert hold["trail_pct"] == 6 and hold["stop"] >= 90
    assert client.patch(f"/api/positions/{p['id']}", json={"trail_pct": 0}, headers=h).json()["trail_pct"] is None


def test_invite_and_isolated_users(client):
    h = _login(client)
    assert client.get("/api/me", headers=h).json()["is_admin"] is True
    client.post("/api/watchlist", json={"symbol": "AAPL"}, headers=h)
    client.put("/api/settings", json={"risk_profile": "aggressive", "report_time": "06:30"}, headers=h)
    inv = client.post("/api/users/invites", json={"note": "Anna"}, headers=h).json()
    assert inv["path"].startswith("/einladung/")
    assert client.get(f"/api/auth/invite/{inv['token']}").json()["invited_by"] == "till"
    r = client.post("/api/auth/register", json={"token": inv["token"], "username": "anna", "password": "annas-pass1"})
    assert r.status_code == 200
    ha = {"Authorization": f"Bearer {r.json()['token']}"}
    # Einladung nur einmal
    assert client.post("/api/auth/register", json={"token": inv["token"], "username": "bob",
                                                   "password": "bobs-pass12"}).status_code == 404
    # eigene, leere Daten und eigene Strategie
    assert client.get("/api/watchlist", headers=ha).json() == []
    sa = client.get("/api/settings", headers=ha).json()
    assert sa["is_admin"] is False and "report_time" not in sa["fields"]
    assert sa["fields"]["risk_profile"]["value"] != "aggressive"
    assert client.put("/api/settings", json={"report_time": "05:00"}, headers=ha).status_code == 422
    assert client.put("/api/settings", json={"risk_profile": "conservative"}, headers=ha).status_code == 200
    assert client.get("/api/settings", headers=h).json()["fields"]["risk_profile"]["value"] == "aggressive"
    client.post("/api/watchlist", json={"symbol": "MSFT"}, headers=ha)
    assert [w["symbol"] for w in client.get("/api/watchlist", headers=h).json()] == ["AAPL"]
    pos = client.post("/api/positions", json={"symbol": "AAPL", "quantity": 1, "buy_price": 100,
                                              "buy_date": "2026-01-02"}, headers=h).json()
    assert client.delete(f"/api/positions/{pos['id']}", headers=ha).status_code == 404
    # nur der Admin verwaltet Nutzer und Updates
    assert client.get("/api/users", headers=ha).status_code == 403
    assert client.get("/api/admin/status", headers=ha).status_code == 403
    users = client.get("/api/users", headers=h).json()
    assert [u["username"] for u in users["users"]] == ["till", "anna"] and users["invites"][0]["used_by_name"] == "anna"
    anna = users["users"][1]["id"]
    assert client.delete(f"/api/users/{anna}", headers=h).status_code == 200
    assert client.get("/api/me", headers=ha).status_code == 401


def test_report_push_is_short_and_links_to_site(client, monkeypatch):
    from app import notify
    sent = []
    monkeypatch.setattr(notify.requests, "post", lambda url, data, headers, timeout: sent.append((url, data, headers)) or
                        type("R", (), {"raise_for_status": lambda self: None})())
    h = _login(client)
    client.post("/api/watchlist", json={"symbol": "AAPL"}, headers=h)
    client.put("/api/settings", json={"ntfy_topic": "test", "app_url": "http://th.local:8080/"}, headers=h)
    assert client.post("/api/report/send", headers=h).status_code == 200
    url, body, headers = sent[-1]
    assert headers["Click"].startswith("http://th.local:8080/?bericht=")
    assert b"Werte gepr" in body and b"Score" not in body  # kurz, keine Details
    rid = int(headers["Click"].rsplit("=", 1)[1])
    rep = client.get(f"/api/reports/{rid}", headers=h).json()
    assert rep["entries"][0]["symbol"] == "AAPL" and client.get("/api/reports/latest", headers=h).json()["id"] == rid


def test_chart_layouts(client):
    h = _login(client)
    d = client.get("/api/charts/AAPL", headers=h).json()
    assert d["updated_at"] is None and [i["kind"] for i in d["indicators"]] == ["sma", "sma", "volume"]
    layout = {"type": "line", "period": "1y", "interval": "1d",
              "indicators": [{"id": "r", "kind": "rsi", "params": {"period": 14}, "color": "#ffffff"}],
              "drawings": [{"id": "a", "kind": "hline", "points": [{"time": 1, "price": 180.5}], "label": "Widerstand"},
                           {"id": "b", "kind": "trend", "points": [{"time": 1, "price": 1}, {"time": 2, "price": 2}]}]}
    r = client.put("/api/charts/aapl", json=layout, headers=h)
    assert r.status_code == 200 and r.json()["drawings"][0]["label"] == "Widerstand"
    assert client.get("/api/charts", headers=h).json()[0]["symbol"] == "AAPL"
    bad = {**layout, "drawings": [{"id": "x", "kind": "kreis", "points": [{"time": 1, "price": 1}]}]}
    assert client.put("/api/charts/AAPL", json=bad, headers=h).status_code == 422
    assert client.put("/api/charts/AAPL", json={**layout, "drawings": [{"id": "x", "kind": "hline", "points": [
        {"time": 1, "price": 1}], "color": "red"}]}, headers=h).status_code == 422
    assert client.delete("/api/charts/AAPL", headers=h).json() == {"ok": True}
