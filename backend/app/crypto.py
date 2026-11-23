"""Verschlüsselung von Geheimnissen in der Datenbank (2FA-Schlüssel, Bank-PIN, FinTS-Sitzungsdaten).

Schlüssel: aus SECRET_KEY abgeleitet (SHA-256 mit eigenem Zweck-Präfix), Verfahren: Fernet (AES-128-CBC + HMAC).
Wer die Datenbank allein in die Hände bekommt, kann damit nichts anfangen; wer zusätzlich die .env hat, schon –
die .env gehört also genauso geschützt wie bisher.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

PREFIX = "f1:"


class CryptoError(ValueError):
    pass


def _fernet(secret: str, purpose: str) -> Fernet:
    key = hashlib.sha256(f"tradehelper:{purpose}:".encode() + secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(text: str, secret: str, purpose: str = "secret") -> str:
    if text == "":
        return ""
    return PREFIX + _fernet(secret, purpose).encrypt(text.encode()).decode()


def decrypt(token: str, secret: str, purpose: str = "secret") -> str:
    if not token:
        return ""
    if not token.startswith(PREFIX):
        raise CryptoError("Unbekanntes Format")
    try:
        return _fernet(secret, purpose).decrypt(token[len(PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise CryptoError("Entschlüsseln nicht möglich (wurde SECRET_KEY geändert?)") from exc


def encrypt_bytes(data: bytes, secret: str, purpose: str) -> str:
    return encrypt(base64.b64encode(data).decode(), secret, purpose)


def decrypt_bytes(token: str, secret: str, purpose: str) -> bytes:
    text = decrypt(token, secret, purpose)
    return base64.b64decode(text) if text else b""
