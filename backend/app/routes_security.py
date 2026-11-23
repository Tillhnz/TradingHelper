"""Zwei-Faktor-Anmeldung und gemerkte Geräte."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import crypto, twofa
from .config import settings as base_settings
from .deps import _fail, _rate_limit, current_user, get_storage, needs_2fa_setup, require_admin
from .security import create_token, read_token, verify_password
from .storage import Storage

router = APIRouter()
PURPOSE = "totp"
CHALLENGE_SECONDS = 300
SETUP_SECONDS = 900


def _secret_of(user: dict) -> str:
    try:
        return crypto.decrypt(user.get("totp_secret") or "", base_settings.secret_key, PURPOSE)
    except crypto.CryptoError:
        return ""


def check_code(st: Storage, user: dict, code: str) -> str | None:
    """Prüft einen 6-stelligen Code oder einen Wiederherstellungscode. Gibt die Art zurück ("totp"/"recovery")."""
    code = (code or "").strip()
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) == twofa.DIGITS and len(code.replace(" ", "")) == twofa.DIGITS:
        step = twofa.verify(_secret_of(user), digits)
        if step is not None and st.use_totp_step(user["id"], step):
            return "totp"
        return None
    if len("".join(ch for ch in code if ch.isalnum())) == 10 and st.use_recovery_code(user["id"], twofa.hash_code(code)):
        return "recovery"
    return None


def login_result(st: Storage, user: dict, request: Request, remember: bool = False, name: str = "") -> dict:
    out = {"token": create_token(user["id"], user["token_version"], base_settings.secret_key)}
    if remember:
        token = twofa.new_device_token()
        st.add_device(user["id"], twofa.hash_device(token), name or twofa.device_name(request.headers.get("user-agent")),
                      base_settings.trusted_device_days)
        out["device"] = token
        out["device_days"] = base_settings.trusted_device_days
    return out


def password_step(st: Storage, user: dict, device: str | None) -> dict:
    """Nach korrektem Passwort: entweder direkt anmelden (keine 2FA oder gemerktes Gerät) oder Code anfordern."""
    if not user.get("totp_enabled"):
        return {"token": create_token(user["id"], user["token_version"], base_settings.secret_key)}
    if device and st.device(user["id"], twofa.hash_device(device)):
        return {"token": create_token(user["id"], user["token_version"], base_settings.secret_key), "remembered": True}
    return {"two_factor": True,
            "challenge": create_token(user["id"], user["token_version"], base_settings.secret_key, purpose="2fa",
                                      seconds=CHALLENGE_SECONDS)}


class Verify(BaseModel):
    challenge: str = Field(min_length=10, max_length=600)
    code: str = Field(min_length=4, max_length=20)
    remember: bool = False
    device_name: str = Field(default="", max_length=80)


@router.post("/api/auth/2fa/verify")
def verify_login(data: Verify, request: Request, st: Storage = Depends(get_storage)):
    """Zweiter Schritt der Anmeldung: Code aus der App (oder Wiederherstellungscode)."""
    _rate_limit(request, ":2fa")
    claim = read_token(data.challenge, base_settings.secret_key)
    if not claim or claim.get("p") != "2fa":
        raise HTTPException(401, "Die Anmeldung ist abgelaufen. Bitte noch einmal mit Passwort anmelden.")
    user = st.get_user(user_id=int(claim["sub"]))
    if not user or user["token_version"] != claim.get("tv") or not user.get("totp_enabled"):
        raise HTTPException(401, "Die Anmeldung ist abgelaufen. Bitte noch einmal mit Passwort anmelden.")
    kind = check_code(st, user, data.code)
    if not kind:
        _fail(request, ":2fa")
        raise HTTPException(401, "Der Code stimmt nicht (oder wurde schon benutzt).")
    out = login_result(st, user, request, data.remember, data.device_name)
    if kind == "recovery":
        out["recovery_left"] = st.recovery_codes_left(user["id"])
    return out


@router.get("/api/auth/2fa")
def status(user: dict = Depends(current_user), st: Storage = Depends(get_storage)):
    return {"enabled": bool(user.get("totp_enabled")), "required": bool(base_settings.require_2fa),
            "needs_setup": needs_2fa_setup(user), "recovery_left": st.recovery_codes_left(user["id"]),
            "devices": st.devices(user["id"]), "device_days": base_settings.trusted_device_days}


@router.post("/api/auth/2fa/setup")
def setup(user: dict = Depends(current_user)):
    """Neuen Schlüssel erzeugen. Aktiv wird er erst mit dem ersten richtigen Code (enable)."""
    secret = twofa.new_secret()
    uri = twofa.otpauth_uri(secret, user["username"])
    pending = create_token(user["id"], user["token_version"], base_settings.secret_key, purpose="2fa-setup",
                           seconds=SETUP_SECONDS)
    return {"secret": secret, "secret_grouped": " ".join(secret[i:i + 4] for i in range(0, len(secret), 4)),
            "uri": uri, "qr_svg": twofa.qr_svg(uri),
            "pending": pending + "." + crypto.encrypt(secret, base_settings.secret_key, "2fa-pending")}


class Enable(BaseModel):
    pending: str = Field(min_length=10, max_length=1200)
    code: str = Field(min_length=6, max_length=10)
    remember: bool = True


@router.post("/api/auth/2fa/enable")
def enable(data: Enable, request: Request, user: dict = Depends(current_user), st: Storage = Depends(get_storage)):
    _rate_limit(request, ":2fa")
    token, _, enc = data.pending.rpartition(".")
    claim = read_token(token, base_settings.secret_key)
    if not claim or claim.get("p") != "2fa-setup" or int(claim["sub"]) != user["id"]:
        raise HTTPException(400, "Die Einrichtung ist abgelaufen. Bitte neu starten.")
    try:
        secret = crypto.decrypt(enc, base_settings.secret_key, "2fa-pending")
    except crypto.CryptoError as exc:
        raise HTTPException(400, "Die Einrichtung ist abgelaufen. Bitte neu starten.") from exc
    step = twofa.verify(secret, data.code)
    if step is None:
        _fail(request, ":2fa")
        raise HTTPException(422, "Der Code passt nicht. Uhrzeit am Handy prüfen und den aktuellen Code eingeben.")
    st.set_totp(user["id"], crypto.encrypt(secret, base_settings.secret_key, PURPOSE), True)
    st.use_totp_step(user["id"], step)
    codes = twofa.new_recovery_codes()
    st.set_recovery_codes(user["id"], [twofa.hash_code(c) for c in codes])
    fresh = st.get_user(user_id=user["id"])
    out = {"recovery_codes": codes}
    if data.remember:  # dieses Gerät gleich merken – sonst fragt die nächste Anmeldung sofort wieder
        out.update({k: v for k, v in login_result(st, fresh, request, True).items() if k != "token"})
    return out


class Confirm(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    code: str = Field(default="", max_length=20)


def _confirm(data: Confirm, request: Request, st: Storage, user: dict) -> None:
    _rate_limit(request, ":2fa")
    if not verify_password(data.password, user["password_hash"]) or (
            user.get("totp_enabled") and not check_code(st, user, data.code)):
        _fail(request, ":2fa")
        raise HTTPException(403, "Passwort oder Code stimmt nicht.")


@router.post("/api/auth/2fa/recovery")
def new_recovery(data: Confirm, request: Request, user: dict = Depends(current_user), st: Storage = Depends(get_storage)):
    """Neue Wiederherstellungscodes (die alten werden ungültig)."""
    if not user.get("totp_enabled"):
        raise HTTPException(409, "Zwei-Faktor-Anmeldung ist nicht eingerichtet.")
    _confirm(data, request, st, user)
    codes = twofa.new_recovery_codes()
    st.set_recovery_codes(user["id"], [twofa.hash_code(c) for c in codes])
    return {"recovery_codes": codes}


@router.post("/api/auth/2fa/disable")
def disable(data: Confirm, request: Request, user: dict = Depends(current_user), st: Storage = Depends(get_storage)):
    if base_settings.require_2fa:
        raise HTTPException(409, "Die Zwei-Faktor-Anmeldung ist auf diesem Server Pflicht. Neu einrichten geht über "
                                 "„Neues Handy“.")
    _confirm(data, request, st, user)
    st.set_totp(user["id"], "", False)
    return {"ok": True}


@router.delete("/api/auth/2fa/devices/{device_id}")
def forget_device(device_id: int, user: dict = Depends(current_user), st: Storage = Depends(get_storage)):
    if not st.delete_device(user["id"], device_id):
        raise HTTPException(404, "Gerät nicht gefunden")
    return {"ok": True}


@router.delete("/api/auth/2fa/devices")
def forget_all_devices(user: dict = Depends(current_user), st: Storage = Depends(get_storage)):
    return {"removed": st.delete_device(user["id"])}


@router.post("/api/users/{user_id}/reset-2fa", dependencies=[Depends(require_admin)])
def admin_reset(user_id: int, st: Storage = Depends(get_storage)):
    """Admin: 2FA eines Nutzers zurücksetzen (Handy verloren, keine Codes mehr). Er richtet sie beim nächsten
    Anmelden neu ein."""
    if not st.get_user(user_id=user_id):
        raise HTTPException(404, "Nutzer nicht gefunden")
    st.set_totp(user_id, "", False)
    return {"ok": True}
