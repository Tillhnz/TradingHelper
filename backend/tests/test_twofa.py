import base64

import pytest

from app import crypto, twofa


def test_rfc6238_vector():
    secret = base64.b32encode(b"12345678901234567890").decode()
    # RFC 6238, Anhang B (SHA-1): T=59 → 94287082 (letzte 6 Ziffern)
    assert twofa.code_at(secret, 59 // 30) == "287082"
    assert twofa.code_at(secret, 1111111109 // 30) == "081804"


def test_verify_window_and_format():
    s = twofa.new_secret()
    now = 1_700_000_000
    step = twofa.current_step(now)
    assert twofa.verify(s, twofa.code_at(s, step), now) == step
    assert twofa.verify(s, twofa.code_at(s, step - 1), now) == step - 1
    assert twofa.verify(s, twofa.code_at(s, step - 3), now) is None
    c = twofa.code_at(s, step)
    assert twofa.verify(s, f"{c[:3]} {c[3:]}", now) == step
    assert twofa.verify(s, "12345", now) is None
    assert twofa.verify("", c, now) is None


def test_recovery_codes_and_devices():
    codes = twofa.new_recovery_codes()
    assert len(codes) == 10 and len(set(codes)) == 10
    c = codes[0]
    assert twofa.hash_code(c) == twofa.hash_code(c.upper().replace("-", " "))
    assert twofa.hash_device("a") != twofa.hash_device("b")
    assert twofa.device_name("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Safari/604.1") == "Safari auf iPhone"


def test_otpauth_uri():
    uri = twofa.otpauth_uri("ABC", "till heinz")
    assert uri.startswith("otpauth://totp/TradeHelper%3Atill%20heinz?secret=ABC&issuer=TradeHelper")


def test_crypto_roundtrip():
    tok = crypto.encrypt("geheim", "key1", "x")
    assert tok.startswith("f1:") and "geheim" not in tok
    assert crypto.decrypt(tok, "key1", "x") == "geheim"
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(tok, "key2", "x")
    with pytest.raises(crypto.CryptoError):
        crypto.decrypt(tok, "key1", "anderer-zweck")
    assert crypto.decrypt_bytes(crypto.encrypt_bytes(b"\x00\x01", "k", "p"), "k", "p") == b"\x00\x01"


def test_storage_totp_replay_and_devices(tmp_path):
    from app.storage import Storage

    st = Storage(tmp_path / "t.db")
    uid = st.create_user("till", "x")
    st.set_totp(uid, "enc", True)
    assert st.use_totp_step(uid, 100) and not st.use_totp_step(uid, 100) and not st.use_totp_step(uid, 99)
    st.set_recovery_codes(uid, ["h1", "h2"])
    assert st.use_recovery_code(uid, "h1") and not st.use_recovery_code(uid, "h1")
    assert st.recovery_codes_left(uid) == 1
    st.add_device(uid, "dev", "Safari auf Mac", 30)
    assert st.device(uid, "dev") and not st.device(uid, "other")
    assert len(st.devices(uid)) == 1
    st.reset_admin_login()
    assert st.get_user(user_id=uid)["totp_enabled"] == 0 and not st.devices(uid)
