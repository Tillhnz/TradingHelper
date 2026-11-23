"""Gemeinsame Abhängigkeiten der API-Routen: Datenbank, Anmeldung, Admin-Prüfung, Schutz vor Rateversuchen."""

from __future__ import annotations

import time

from fastapi import Depends, Header, HTTPException, Request

from . import settings_store
from .config import Settings
from .config import settings as base_settings
from .security import read_token
from .storage import Storage

_storage: Storage | None = None

# Diese Pfade gehen auch, solange die Pflicht-2FA noch nicht eingerichtet ist
TWOFA_SETUP_PATHS = ("/api/me", "/api/version", "/api/auth/2fa", "/api/auth/password", "/api/auth/logout")
TWOFA_REQUIRED = "2FA_SETUP_REQUIRED"


def get_storage() -> Storage:
    """Datenbank für server-weite Dinge (Anmeldung, Nutzerverwaltung). Nutzerdaten: user_storage."""
    global _storage
    if _storage is None or _storage.path != str(base_settings.db_path):
        _storage = Storage(base_settings.db_path)
    return _storage


def needs_2fa_setup(user: dict) -> bool:
    return bool(base_settings.require_2fa) and not user.get("totp_enabled")


def current_user(request: Request, authorization: str | None = Header(default=None),
                 st: Storage = Depends(get_storage)) -> dict:
    unauthorized = HTTPException(401, "Nicht angemeldet")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized
    data = read_token(authorization[7:], base_settings.secret_key)
    if not data or data.get("p"):  # Zweck-Tokens (z. B. für den 2FA-Schritt) sind keine Anmeldung
        raise unauthorized
    user = st.get_user(user_id=int(data["sub"]))
    if not user or user["token_version"] != data.get("tv") or not user["password_hash"]:
        raise unauthorized
    if needs_2fa_setup(user) and not request.url.path.startswith(TWOFA_SETUP_PATHS):
        raise HTTPException(403, f"{TWOFA_REQUIRED}: Bitte zuerst die Zwei-Faktor-Anmeldung einrichten.")
    return user


def user_storage(user: dict = Depends(current_user)) -> Storage:
    """Datenbank, gebunden an den angemeldeten Nutzer: er sieht nur seine eigenen Daten."""
    return get_storage().for_user(user["id"])


def user_cfg(st: Storage = Depends(user_storage)) -> Settings:
    """Einstellungen des angemeldeten Nutzers (server-weite plus persönliche)."""
    return settings_store.for_user(st, base_settings)


def require_admin(user: dict = Depends(current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(403, "Nur der Admin darf das.")
    return user


auth = [Depends(current_user)]
admin_only = [Depends(require_admin)]

_fails: dict[str, list[float]] = {}


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _rate_limit(request: Request, key: str = "") -> None:
    ip = client_ip(request) + key
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < 600]
    _fails[ip] = recent
    if len(recent) >= 8:
        raise HTTPException(429, "Zu viele Fehlversuche. Bitte in einigen Minuten erneut versuchen.")


def _fail(request: Request, key: str = "") -> None:
    _fails.setdefault(client_ip(request) + key, []).append(time.time())
