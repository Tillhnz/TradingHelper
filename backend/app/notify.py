"""Benachrichtigungen über ntfy (https://ntfy.sh oder selbst gehostet)."""

from __future__ import annotations

import logging

import requests

from .config import Settings

log = logging.getLogger(__name__)

last_error = ""  # Grund des letzten fehlgeschlagenen Versands (für das Job-Protokoll)


def link(settings: Settings, path: str = "/") -> str | None:
    """Adresse in der Oberfläche, die beim Antippen der Benachrichtigung geöffnet wird."""
    base = (getattr(settings, "app_url", "") or "").rstrip("/")
    return f"{base}{path if path.startswith('/') else '/' + path}" if base else None


def send(settings: Settings, title: str, message: str, priority: str = "default",
         tags: list[str] | None = None, click: str | None = None, path: str = "/") -> bool:
    """Push über ntfy. Beim Antippen öffnet sich die Oberfläche (app_url + path), sofern die Adresse bekannt ist."""
    global last_error
    last_error = ""
    if not settings.ntfy_topic:
        last_error = "kein ntfy-Topic hinterlegt"
        log.warning("TH_NTFY_TOPIC nicht gesetzt – Nachricht nur geloggt: %s | %s", title, message)
        return False

    url = f"{settings.ntfy_url.rstrip('/')}/{settings.ntfy_topic}"
    headers = {
        # Header müssen latin-1-kodierbar sein; ntfy unterstützt RFC 2047 nicht zuverlässig,
        # daher Umlaute im Titel ersetzen und Nachricht als UTF-8-Body senden.
        "Title": title.encode("latin-1", "replace").decode("latin-1"),
        "Priority": priority,
        "Markdown": "yes",
    }
    if tags:
        headers["Tags"] = ",".join(tags)
    click = click or link(settings, path)
    if click:
        headers["Click"] = click
    if settings.ntfy_token:
        headers["Authorization"] = f"Bearer {settings.ntfy_token}"

    try:
        r = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=15)
        r.raise_for_status()
        return True
    except requests.RequestException as exc:
        last_error = str(exc)[:300]
        log.error("ntfy-Versand fehlgeschlagen: %s", exc)
        return False
