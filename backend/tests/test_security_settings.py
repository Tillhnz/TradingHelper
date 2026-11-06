import time

import pytest

from app import security, settings_store
from app.config import Settings
from app.storage import Storage


def test_password_hash_roundtrip():
    h = security.hash_password("geheim123")
    assert security.verify_password("geheim123", h)
    assert not security.verify_password("falsch", h)
    assert not security.verify_password("x", "kaputt")


def test_token_roundtrip_and_tamper():
    t = security.create_token(1, 0, "s3cret")
    assert security.read_token(t, "s3cret")["sub"] == 1
    assert security.read_token(t, "anders") is None
    payload, sig = t.split(".")
    assert security.read_token(payload + "x." + sig, "s3cret") is None
    assert security.read_token("unsinn", "s3cret") is None


def test_token_expiry(monkeypatch):
    t = security.create_token(1, 0, "s", days=1)
    monkeypatch.setattr(time, "time", lambda: 10**11)
    assert security.read_token(t, "s") is None


def test_settings_save_and_override(tmp_path):
    st = Storage(tmp_path / "t.db")
    s = Settings(data_dir=tmp_path)
    changed = settings_store.save(st, s, {"report_time": "6:45", "risk_profile": "conservative", "ntfy_topic": "mein-topic"})
    assert set(changed) == {"report_time", "risk_profile", "ntfy_topic"}
    assert s.report_time == "06:45" and s.risk_profile == "conservative"

    fresh = Settings(data_dir=tmp_path)
    settings_store.apply_overrides(st, fresh)
    assert fresh.report_time == "06:45" and fresh.ntfy_topic == ""  # Push-Kanal ist persönlich
    mine = settings_store.for_user(st, fresh)
    assert mine.ntfy_topic == "mein-topic" and mine.risk_profile == "conservative" and mine.report_time == "06:45"
    other = settings_store.for_user(st.for_user(2), fresh)
    assert other.ntfy_topic == "" and other.risk_profile == fresh.risk_profile


def test_settings_user_scope_and_admin_only(tmp_path):
    st = Storage(tmp_path / "t.db")
    base = Settings(data_dir=tmp_path)
    anna = st.for_user(2)
    cfg = settings_store.for_user(anna, base)
    settings_store.save(anna, cfg, {"risk_profile": "aggressive"}, base, is_admin=False)
    assert cfg.risk_profile == "aggressive" and base.risk_profile != "aggressive"
    with pytest.raises(settings_store.SettingError):
        settings_store.save(anna, cfg, {"report_time": "05:00"}, base, is_admin=False)
    desc = settings_store.describe(anna, cfg, is_admin=False)
    assert "report_time" not in desc and desc["risk_profile"]["scope"] == "user"


def test_old_global_user_settings_move_to_owner(tmp_path):
    st = Storage(tmp_path / "t.db")
    st.create_user("till", "h")
    st.set_app_setting("risk_profile", "aggressive")
    st.set_app_setting("report_time", "06:00")
    base = Settings(data_dir=tmp_path)
    settings_store.apply_overrides(st, base)
    assert "risk_profile" not in st.app_settings() and st.user_settings() == {"risk_profile": "aggressive"}
    assert base.report_time == "06:00"


def test_settings_secrets_hidden_and_kept(tmp_path):
    st = Storage(tmp_path / "t.db")
    s = Settings(data_dir=tmp_path)
    settings_store.save(st, s, {"finnhub_api_key": "abc"})
    desc = settings_store.describe(st, s)
    assert desc["finnhub_api_key"] == {"group": "news", "secret": True, "from_ui": True, "type": "str:100", "set": True,
                                       "scope": "server"}
    settings_store.save(st, s, {"finnhub_api_key": None})  # None = behalten
    assert s.finnhub_api_key == "abc"
    settings_store.save(st, s, {"finnhub_api_key": ""})  # leer = löschen
    assert s.finnhub_api_key == ""


@pytest.mark.parametrize("key,value", [
    ("report_time", "25:00"), ("invest_horizon", "ewig"), ("risk_profile", "yolo"), ("portfolio_size", "-5"), ("timezone", "Mars/Olymp"),
    ("ntfy_topic", "mit leerzeichen"), ("ntfy_url", "ftp://x"), ("alert_interval_minutes", "7"), ("unbekannt", 1),
])
def test_settings_validation(tmp_path, key, value):
    st = Storage(tmp_path / "t.db")
    with pytest.raises(settings_store.SettingError):
        settings_store.save(st, Settings(data_dir=tmp_path), {key: value})


def test_user_storage(tmp_path):
    st = Storage(tmp_path / "t.db")
    assert st.user_count() == 0
    uid = st.create_user("till", "hash")
    assert st.get_user(username="TILL")["id"] == uid
    st.set_password(uid, "neu")
    assert st.get_user(user_id=uid)["token_version"] == 1
    assert st.users()[0]["is_admin"] == 1
