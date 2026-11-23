"""Zwei-Faktor-Anmeldung mit einer Authenticator-App (TOTP nach RFC 6238: 6 Ziffern, 30 Sekunden, SHA-1).

Funktioniert mit allen gängigen Apps (Google/Microsoft Authenticator, 2FAS, Aegis, 1Password, Bitwarden …).
* Ein Code gilt im aktuellen 30-Sekunden-Fenster und je eines davor/danach (Uhr-Abweichung). Jeder Code ist nur
  einmal gültig (Wiederholungsschutz über den zuletzt benutzten Zeitschritt).
* Zehn Wiederherstellungscodes (je einmal nutzbar), falls das Handy weg ist. Gespeichert wird nur ihr Hash.
* „Gerät merken“: Das Gerät bekommt ein zufälliges Geräte-Token (nur der Hash liegt in der Datenbank). Mit gültigem
  Token entfällt der Code bei der Anmeldung für die eingestellte Zahl an Tagen; das Passwort bleibt nötig.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
import struct
import time
from urllib.parse import quote

DIGITS = 6
PERIOD = 30
WINDOW = 1
ISSUER = "TradeHelper"


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    s = secret.strip().replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def code_at(secret: str, step: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10 ** DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((now if now is not None else time.time()) // PERIOD)


def verify(secret: str, code: str, now: float | None = None, window: int = WINDOW) -> int | None:
    """Zeitschritt des passenden Codes oder None."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != DIGITS or not secret:
        return None
    step = current_step(now)
    for s in range(step - window, step + window + 1):
        if hmac.compare_digest(code_at(secret, s), code):
            return s
    return None


def otpauth_uri(secret: str, username: str, issuer: str = ISSUER) -> str:
    label = quote(f"{issuer}:{username}")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={PERIOD}")


def qr_svg(text: str) -> str | None:
    """QR-Code als SVG (segno, falls installiert). Ohne segno zeigt die Oberfläche den Schlüssel zum Abtippen."""
    try:
        import segno
    except ImportError:
        return None
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="svg", scale=5, border=2, dark="#1f1e1d", light="#ffffff",
                                     xmldecl=False, svgns=True)
    return buf.getvalue().decode()


# ---------- Wiederherstellungscodes ----------

_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # ohne 0/o/1/l/i


def new_recovery_codes(n: int = 10) -> list[str]:
    def one() -> str:
        raw = "".join(secrets.choice(_ALPHABET) for _ in range(10))
        return f"{raw[:5]}-{raw[5:]}"
    return [one() for _ in range(n)]


def normalize_recovery(code: str) -> str:
    c = "".join(ch for ch in code.lower() if ch.isalnum())
    return f"{c[:5]}-{c[5:]}" if len(c) == 10 else c


def hash_code(code: str) -> str:
    return hashlib.sha256(("th-recovery:" + normalize_recovery(code)).encode()).hexdigest()


# ---------- Geräte ----------

def new_device_token() -> str:
    return secrets.token_urlsafe(32)


def hash_device(token: str) -> str:
    return hashlib.sha256(("th-device:" + token).encode()).hexdigest()


def device_name(user_agent: str | None) -> str:
    """Kurzer, verständlicher Gerätename aus dem User-Agent („Safari auf iPhone“)."""
    ua = (user_agent or "").lower()
    browser = next((b for k, b in [("edg/", "Edge"), ("firefox", "Firefox"), ("chrome", "Chrome"),
                                   ("safari", "Safari")] if k in ua), "Browser")
    system = next((s for k, s in [("iphone", "iPhone"), ("ipad", "iPad"), ("android", "Android"),
                                  ("mac os", "Mac"), ("windows", "Windows"), ("linux", "Linux")] if k in ua), "")
    return f"{browser} auf {system}" if system else browser
