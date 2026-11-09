"""Update-Wächter: meldet Administratoren per Push (ntfy), sobald auf GitHub eine neue Version bereitliegt.

Fragt alle 6 Stunden den Update-Dienst (git fetch) und meldet jede neue Version genau einmal. Enthält sie
Paket- oder Sicherheitsupdates (z. B. von Dependabot), kommt die Meldung mit hoher Priorität.
"""
from __future__ import annotations

import logging
import re

from . import notify, settings_store, updater_client
from .config import Settings
from .storage import Storage

log = logging.getLogger(__name__)
KEY = "_update_notified"
SECURITY = re.compile(r"\b(bump|sicherheit|security|cve-|lücke|vulnerab|dependabot)\b", re.I)


def describe(changes: list[str], behind: int) -> tuple[bool, str]:
    subjects = [c.split("  ", 1)[-1] for c in changes]
    sec = any(SECURITY.search(s) for s in subjects)
    lines = "\n".join(f"- {s}" for s in subjects[:8]) + (f"\n- … und {behind - 8} weitere" if behind > 8 else "")
    return sec, lines


def run(storage: Storage, base: Settings, fetch_status=None, send=None) -> int:
    """Gibt die Zahl verschickter Meldungen zurück."""
    if not base.update_notify:
        return 0
    try:
        st = (fetch_status or (lambda: updater_client.call("GET", "/status?check=1", timeout=120)))()
    except Exception as e:  # noqa: BLE001 - kein Update-Dienst oder nicht erreichbar
        log.info("Update-Prüfung nicht möglich: %s", getattr(e, "detail", e))
        return 0
    behind, changes = st.get("behind") or 0, st.get("changes") or []
    if not behind or not changes or storage.app_settings().get(KEY) == changes[0]:
        return 0
    sec, lines = describe(changes, behind)
    title = ("Sicherheitsupdate" if sec else "Neue Version") + " für TradeHelper verfügbar"
    body = f"{behind} {'Änderung' if behind == 1 else 'Änderungen'}:\n{lines}\n\nEinspielen: Einstellungen → Update."
    sent = 0
    for u in storage.users():
        if not u["is_admin"]:
            continue
        cfg = settings_store.for_user(storage.for_user(u["id"]), base)
        if (send or notify.send)(cfg, title, body, priority="high" if sec else "default", tags=["package"], path="/settings"):
            sent += 1
    storage.set_app_setting(KEY, changes[0])
    return sent
