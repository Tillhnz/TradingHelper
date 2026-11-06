"""Kleine Notfall-Befehle für das Terminal: python -m app.cli <befehl>."""

from __future__ import annotations

import sys

from .config import settings
from .storage import Storage


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else ""
    st = Storage(settings.db_path)
    if cmd == "reset-login":
        ok = st.reset_admin_login()
        print("Anmeldung des Admins zurückgesetzt. Beim nächsten Aufruf der Oberfläche legst du Benutzername und "
              "Passwort neu fest; alle Daten bleiben erhalten." if ok else "Es gab noch kein Konto.")
        return 0
    print("Befehle: reset-login")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
