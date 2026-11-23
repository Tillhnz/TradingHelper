"""Depots bei Banken und Brokern – per Upload von Umsatzlisten (CSV) oder Wertpapierabrechnungen (PDF).

Jeder Kauf wird ein Block im Depot, jeder Verkauf schließt einen Block. Doppelt hochgeladene Dateien werden erkannt.
Eine CSV ohne Kauf/Verkauf-Spalte, aber mit ISIN und Stückzahl, gilt als Bestandsliste (Depotaufstellung).
TradeHelper verbindet sich mit keiner Bank und kann keine Aufträge erteilen.
"""

from __future__ import annotations

import re

_HINT = ("Umsatzliste als CSV oder Wertpapierabrechnungen als PDF hochladen – auch viele auf einmal. Doppelte Käufe "
         "erkennt TradeHelper. Eine CSV mit ISIN und Stückzahl ohne Kauf/Verkauf gilt als aktueller Bestand.")

BANKS: dict[str, dict] = {
    "consorsbank": {"name": "Consorsbank", "kind": "import",
                    "import_hint": "Im Online-Banking unter Depot → Umsätze bzw. Depotübersicht als CSV exportieren "
                                   "oder die Abrechnungen (PDF) aus dem Postfach laden. " + _HINT},
    "commerzbank": {"name": "Commerzbank", "kind": "import",
                    "import_hint": "Im Online-Banking unter Depot → Umsätze bzw. Bestand als CSV exportieren oder die "
                                   "Wertpapierabrechnungen (PDF) aus dem Postfach laden. " + _HINT},
    "finanzen_zero": {"name": "finanzen.net zero", "kind": "import",
                      "import_hint": "In der App bzw. auf finanzen.net/zero unter Depot → Umsätze die CSV laden oder "
                                     "die PDF-Abrechnungen (Baader Bank) aus dem Postfach. " + _HINT},
    "import": {"name": "Anderer Broker", "kind": "import", "import_hint": _HINT},
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
