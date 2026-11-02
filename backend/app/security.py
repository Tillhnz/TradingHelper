"""Anmeldung ohne Zusatzbibliotheken: PBKDF2-Passwörter und HMAC-signierte Tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

ITERATIONS = 390_000
TOKEN_DAYS = 30


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters))
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(dk.hex(), digest)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def create_token(user_id: int, token_version: int, secret: str, days: int = TOKEN_DAYS) -> str:
    payload = _b64(json.dumps({"sub": user_id, "tv": token_version, "exp": int(time.time()) + days * 86400}).encode())
    sig = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_token(token: str, secret: str) -> dict | None:
    try:
        payload, sig = token.split(".")
    except ValueError:
        return None
    expected = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(_unb64(payload))
    except ValueError:
        return None
    if data.get("exp", 0) < time.time():
        return None
    return data
