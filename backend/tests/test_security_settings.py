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
    changed = settings_store.save(st, s, {"report_time": "6:45", "news_weight": "40", "ntfy_topic": "mein-topic"})
    assert set(changed) == {"report_time", "news_weight", "ntfy_topic"}
    assert s.report_time == "06:45" and s.news_weight == 40

    fresh = Settings(data_dir=tmp_path)
    settings_store.apply_overrides(st, fresh)
    assert fresh.report_time == "06:45" and fresh.ntfy_topic == "mein-topic"


def test_settings_secrets_hidden_and_kept(tmp_path):
    st = Storage(tmp_path / "t.db")
    s = Settings(data_dir=tmp_path)
    settings_store.save(st, s, {"finnhub_api_key": "abc"})
    desc = settings_store.describe(st, s)
    assert desc["finnhub_api_key"] == {"group": "news", "secret": True, "from_ui": True, "type": "str:100", "set": True}
    settings_store.save(st, s, {"finnhub_api_key": None})  # None = behalten
    assert s.finnhub_api_key == "abc"
    settings_store.save(st, s, {"finnhub_api_key": ""})  # leer = löschen
    assert s.finnhub_api_key == ""


@pytest.mark.parametrize("key,value", [
    ("report_time", "25:00"), ("news_weight", "150"), ("timezone", "Mars/Olymp"),
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
    assert st.delete_users() == 1
