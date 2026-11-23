"""Depots bei Banken und Brokern – ausschließlich lesend.

Es gibt drei Wege, je nachdem, was die Bank anbietet:
* FinTS/HBCI (offizieller Bankzugang, nur Abfragen „Depotaufstellung“, nie Aufträge): Consorsbank, Commerzbank,
  comdirect und alle anderen Banken mit FinTS-PIN/TAN-Zugang. → fints_sync.py
* Import von Abrechnungen bzw. Umsatzlisten (CSV oder PDF), z. B. finanzen.net zero (Depotbank Baader Bank), das keine
  Schnittstelle hat. Jeder Kauf wird ein Block im Depot, jeder Verkauf schließt einen Block. → importer.py
* Manuell erfasste Käufe wie bisher.

TradeHelper schickt niemals Aufträge an eine Bank. Der FinTS-Teil benutzt nur die Geschäftsvorfälle Kontenliste
(HKSPA) und Depotaufstellung (HKWPD).
"""

from __future__ import annotations

import re

# Bekannte Zugänge. blz=None: die eigene Bankleitzahl eintragen (z. B. Commerzbank je nach Filiale).
BANKS: dict[str, dict] = {
    "consorsbank": {
        "name": "Consorsbank", "kind": "fints", "blz": "76030080", "url": "https://brokerage-hbci.consorsbank.de/hbci",
        "login_label": "Kontonummer + Berechtigtennummer", "login_hint": "z. B. 1234567890001 (Berechtigte meist 001)",
        "pin_label": "Online-Banking-PIN", "tan_hint": "Freigabe in der Consorsbank-App",
    },
    "commerzbank": {
        "name": "Commerzbank", "kind": "fints", "blz": None, "url": "https://fints.commerzbank.de/fints",
        "login_label": "Teilnehmernummer", "login_hint": "Teilnehmernummer aus dem Online-Banking",
        "pin_label": "PIN", "tan_hint": "photoTAN-App: Grafik scannen oder in der App freigeben",
        "setup_hint": "FinTS mit PIN/TAN muss bei der Commerzbank einmalig freigeschaltet sein (Online-Banking → "
                      "Einstellungen → HBCI/FinTS).",
    },
    "comdirect": {
        "name": "comdirect", "kind": "fints", "blz": "20041111", "url": "https://fints.comdirect.de/fints",
        "login_label": "Zugangsnummer", "login_hint": "8-stellige Zugangsnummer", "pin_label": "PIN",
        "tan_hint": "photoTAN-App",
    },
    "fints": {
        "name": "Andere Bank (FinTS)", "kind": "fints", "blz": None, "url": None,
        "login_label": "Anmeldename / Kundennummer", "login_hint": "wie im Online-Banking", "pin_label": "PIN",
        "tan_hint": "TAN-Verfahren deiner Bank",
    },
    "finanzen_zero": {
        "name": "finanzen.net zero", "kind": "import",
        "import_hint": "In der App bzw. auf finanzen.net/zero unter Depot → Umsätze die CSV-Datei laden oder die "
                       "PDF-Abrechnungen (Postfach) hochladen. Beides darf wiederholt hochgeladen werden – doppelte "
                       "Käufe erkennt TradeHelper.",
    },
    "import": {
        "name": "Anderer Broker (Import)", "kind": "import",
        "import_hint": "CSV-Umsatzliste (Datum, ISIN, Stück, Kurs, Kauf/Verkauf) oder PDF-Abrechnungen hochladen.",
    },
}


class BrokerError(RuntimeError):
    pass


_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d$")


def valid_isin(isin: str) -> bool:
    """Formal und mit Prüfziffer (Luhn über die in Ziffern umgewandelte ISIN)."""
    s = (isin or "").strip().upper()
    if not _ISIN.match(s):
        return False
    digits = "".join(str(int(ch, 36)) for ch in s[:-1])
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return (10 - total % 10) % 10 == int(s[-1])


COUNTRIES = {
    "DE": "Deutschland", "US": "USA", "FR": "Frankreich", "NL": "Niederlande", "GB": "Großbritannien",
    "CH": "Schweiz", "IE": "Irland", "LU": "Luxemburg", "AT": "Österreich", "IT": "Italien", "ES": "Spanien",
    "DK": "Dänemark", "SE": "Schweden", "FI": "Finnland", "NO": "Norwegen", "BE": "Belgien", "JP": "Japan",
    "CA": "Kanada", "AU": "Australien", "CN": "China", "KY": "Kaimaninseln", "TW": "Taiwan", "KR": "Südkorea",
    "IN": "Indien", "BR": "Brasilien", "JE": "Jersey", "BM": "Bermuda", "PT": "Portugal", "PL": "Polen",
}


def country_of(isin: str | None) -> str | None:
    if not isin or len(isin) < 2:
        return None
    return isin[:2].upper()
