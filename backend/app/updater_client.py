"""Verbindung zum Update-Dienst (eigener Container, nur intern erreichbar, mit gemeinsamem Token)."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request

from fastapi import HTTPException

from .config import settings


def token() -> str:
    return hashlib.sha256(("updater:" + settings.secret_key).encode()).hexdigest()


def call(method: str, path: str, timeout: float = 90) -> dict:
    if not settings.updater_url:
        raise HTTPException(503, "Der Update-Dienst ist nicht eingerichtet. Einmalig im Terminal: ./install.sh update")
    req = urllib.request.Request(
        settings.updater_url.rstrip("/") + path, method=method,
        headers={"X-Updater-Token": token()}, data=b"" if method == "POST" else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error", "")
        except ValueError:
            msg = ""
        raise HTTPException(409 if e.code == 409 else 502, msg or f"Update-Dienst meldet Fehler {e.code}.") from e
    except (urllib.error.URLError, OSError) as e:
        raise HTTPException(503, "Der Update-Dienst ist nicht erreichbar. Einmalig im Terminal: ./install.sh update") from e
