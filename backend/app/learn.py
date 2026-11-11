"""Das Stimmungsmodell lernt aus Korrekturen in der App.

Tippt jemand bei einer Meldung auf „klingt positiv“ und wählt „eigentlich negativ“, passiert zweierlei:
1. Genau diese Schlagzeile bekommt künftig die korrigierte Stimmung (auch bei anderen Quellen mit gleichem Titel).
2. Die Wörter der Schlagzeile sammeln Erfahrung: Ein Wort, das mehrmals in negativ korrigierten Meldungen
   vorkommt, zählt künftig selbst leicht negativ – auch in neuen Schlagzeilen. Ein Wort braucht dafür mindestens
   zwei Korrekturen, damit ein einzelner Ausreißer nichts verdirbt.
Die Korrekturen gelten für alle Nutzer dieser Installation.
"""
from __future__ import annotations

import re
import threading

from . import sentiment

_LOCK = threading.Lock()
OVERRIDES: dict[str, int] = {}
TOKENS: dict[str, float] = {}
COUNT = 0

STOP = set((
    "aktie aktien der die das und mit für von auf den dem des ein eine einen im in ist zu nach bei über aus wie was "
    "the and for with from to of on in at is are as its by after stock stocks shares share inc corp ag se this that "
    "it be will has have new neue neuer neues am um an es sich nicht not mehr more than als jetzt now heute today"
).split())


def key(headline: str) -> str:
    """Schlagzeile ohne Quellenzusatz („… - Handelsblatt“) und Satzzeichen – so passen Varianten zusammen."""
    t = sentiment.normalize(headline)
    t = re.split(r" [-–|] (?=[^-–|]{2,40}$)", t)[0]
    return re.sub(r"[^\wäöüß ]+", "", t).strip()


def tokens(headline: str) -> set[str]:
    return {w for w in re.findall(r"[a-zäöüß]{3,}", key(headline)) if w not in STOP}


def refresh(storage) -> None:
    """Modell aus allen gespeicherten Korrekturen neu aufbauen."""
    global OVERRIDES, TOKENS, COUNT
    rows = storage.news_feedback()
    over = {key(r["headline"]): int(r["label"]) for r in rows}
    stats: dict[str, list[int]] = {}
    for h, label in over.items():
        for w in tokens(h):
            s = stats.setdefault(w, [0, 0, 0])  # positiv, neutral, negativ
            s[0 if label > 0 else 2 if label < 0 else 1] += 1
    tok = {}
    for w, (p, n0, n) in stats.items():
        total = p + n0 + n
        if total >= 2 and p != n:
            tok[w] = round((p - n) / (total + 2), 3)
    with _LOCK:
        OVERRIDES, TOKENS, COUNT = over, tok, len(over)


def adjust(headline: str, score: float) -> float:
    """Regel-Wert mit dem Gelernten verrechnen."""
    k = key(headline)
    if k in OVERRIDES:
        return 0.6 * OVERRIDES[k]
    if not TOKENS:
        return score
    learned = [TOKENS[w] for w in tokens(headline) if w in TOKENS]
    if not learned:
        return score
    nudge = max(-0.5, min(0.5, sum(learned)))
    return round(max(-1.0, min(1.0, score + nudge)), 3)
