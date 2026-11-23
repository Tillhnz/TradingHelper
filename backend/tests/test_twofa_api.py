import time

import pytest

from app import twofa

# ---------- API (läuft in der CI mit FastAPI) ----------

fastapi = pytest.importorskip("fastapi")


@pytest.fixture
def client(tmp_path, monkeypatch, uptrend):
    from fastapi.testclient import TestClient

    from app import main, market
    from app.config import settings

    settings.reset()
    settings.data_dir = tmp_path
    settings.scheduler_enabled = False
    settings.secret_key = "test-secret"
    settings.require_2fa = True
    main._fails.clear()
    monkeypatch.setattr(market, "get_history", lambda *a, **k: uptrend)
    monkeypatch.setattr(market, "symbol_info", lambda s: {"symbol": s, "name": "X", "currency": "USD"})
    with TestClient(main.app) as c:
        yield c
    settings.reset()


def _enable(client, h):
    r = client.post("/api/auth/2fa/setup", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    code = twofa.code_at(data["secret"], twofa.current_step())
    r = client.post("/api/auth/2fa/enable", json={"pending": data["pending"], "code": code, "remember": True}, headers=h)
    assert r.status_code == 200, r.text
    return data["secret"], r.json()


def test_required_2fa_gate_and_login_flow(client):
    r = client.post("/api/auth/setup", json={"username": "till", "password": "geheim123"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    # ohne eingerichtete 2FA: nur Einrichtung erlaubt
    assert client.get("/api/me", headers=h).json()["needs_2fa_setup"] is True
    r = client.get("/api/watchlist", headers=h)
    assert r.status_code == 403 and r.json()["detail"].startswith("2FA_SETUP_REQUIRED")
    secret, enabled = _enable(client, h)
    assert len(enabled["recovery_codes"]) == 10 and enabled["device"]
    assert client.get("/api/watchlist", headers=h).status_code == 200

    # Anmeldung ohne Gerät → Code nötig
    r = client.post("/api/auth/login", json={"username": "till", "password": "geheim123"})
    assert r.json()["two_factor"] is True and "token" not in r.json()
    challenge = r.json()["challenge"]
    # das Zweck-Token ist keine Anmeldung
    assert client.get("/api/me", headers={"Authorization": f"Bearer {challenge}"}).status_code == 401
    assert client.post("/api/auth/2fa/verify", json={"challenge": challenge, "code": "000000"}).status_code == 401
    time.sleep(0)  # gleicher Zeitschritt wie bei der Einrichtung wäre schon verbraucht → Wiederherstellungscode
    r = client.post("/api/auth/2fa/verify", json={"challenge": challenge, "code": enabled["recovery_codes"][0],
                                                  "remember": True})
    assert r.status_code == 200, r.text
    assert r.json()["token"] and r.json()["device"] and r.json()["recovery_left"] == 9
    # Code nicht zweimal
    assert client.post("/api/auth/2fa/verify", json={"challenge": challenge, "code": enabled["recovery_codes"][0]}
                       ).status_code == 401

    # mit gemerktem Gerät: direkt rein
    r = client.post("/api/auth/login", json={"username": "till", "password": "geheim123", "device": r.json()["device"]})
    assert r.json().get("token") and r.json().get("remembered")
    # falsches Gerät: wieder Code
    r = client.post("/api/auth/login", json={"username": "till", "password": "geheim123", "device": "falsch"})
    assert r.json()["two_factor"] is True

    st = client.get("/api/auth/2fa", headers=h).json()
    assert st["enabled"] and st["required"] and len(st["devices"]) == 2
    assert client.delete(f"/api/auth/2fa/devices/{st['devices'][0]['id']}", headers=h).status_code == 200
    # Pflicht: abschalten geht nicht
    assert client.post("/api/auth/2fa/disable", json={"password": "geheim123", "code": "x"}, headers=h).status_code == 409
