"""Nachrichten über Finnhub plus regelbasiertes Sentiment (ohne LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import requests

FINNHUB_URL = "https://finnhub.io/api/v1"

# Kleines Finanz-Lexikon (Englisch + Deutsch). Gewichte: +/-1 normal, +/-2 stark.
POSITIVE = {
    "beat": 2, "beats": 2, "surge": 2, "surges": 2, "soar": 2, "soars": 2, "record": 1, "upgrade": 2,
    "upgraded": 2, "outperform": 2, "buy rating": 2, "raises guidance": 2, "raised guidance": 2,
    "strong": 1, "growth": 1, "profit": 1, "rally": 1, "rallies": 1, "jump": 1, "jumps": 1, "gain": 1,
    "gains": 1, "bullish": 2, "partnership": 1, "approval": 1, "approved": 1, "buyback": 1,
    "dividend increase": 2, "exceeds": 1, "tops": 1, "rekord": 1, "steigt": 1, "hochgestuft": 2,
    "kaufempfehlung": 2, "gewinn": 1, "übertrifft": 2, "prognose angehoben": 2, "wachstum": 1,
}
NEGATIVE = {
    "miss": 2, "misses": 2, "plunge": 2, "plunges": 2, "tumble": 2, "tumbles": 2, "downgrade": 2,
    "downgraded": 2, "underperform": 2, "sell rating": 2, "cuts guidance": 2, "lowered guidance": 2,
    "weak": 1, "loss": 1, "losses": 1, "lawsuit": 1, "probe": 1, "investigation": 1, "recall": 1,
    "bearish": 2, "layoffs": 1, "fall": 1, "falls": 1, "drop": 1, "drops": 1, "slump": 2, "fraud": 2,
    "bankruptcy": 2, "warning": 1, "fine": 1, "fällt": 1, "herabgestuft": 2, "verkaufsempfehlung": 2,
    "verlust": 1, "gewinnwarnung": 2, "prognose gesenkt": 2, "klage": 1, "stellenabbau": 1,
}


@dataclass
class NewsItem:
    headline: str
    summary: str
    source: str
    url: str
    published: str
    sentiment: float

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def score_text(text: str) -> float:
    """Sentiment zwischen -1 und +1 auf Basis des Lexikons."""
    t = text.lower()
    pos = sum(w * len(re.findall(rf"\b{re.escape(k)}\b", t)) for k, w in POSITIVE.items())
    neg = sum(w * len(re.findall(rf"\b{re.escape(k)}\b", t)) for k, w in NEGATIVE.items())
    total = pos + neg
    return 0.0 if total == 0 else round((pos - neg) / total, 3)


def finnhub_symbol(symbol: str) -> str:
    """Finnhub-Company-News deckt v. a. US-Ticker ab; Yahoo-Suffixe werden entfernt."""
    return symbol.split(".")[0].replace("-", ".") if not symbol.startswith("^") else symbol


def fetch_news(symbol: str, api_key: str, lookback_days: int = 3, limit: int = 10) -> list[NewsItem]:
    if not api_key:
        return []
    to = date.today()
    frm = to - timedelta(days=lookback_days)
    try:
        r = requests.get(
            f"{FINNHUB_URL}/company-news",
            params={"symbol": finnhub_symbol(symbol), "from": frm.isoformat(), "to": to.isoformat(), "token": api_key},
            timeout=15,
        )
        r.raise_for_status()
        raw = r.json()
    except (requests.RequestException, ValueError):
        return []
    if not isinstance(raw, list):
        return []

    items: list[NewsItem] = []
    for n in raw[:limit]:
        headline = n.get("headline", "")
        summary = n.get("summary", "")
        ts = n.get("datetime")
        published = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else ""
        items.append(
            NewsItem(headline, summary, n.get("source", ""), n.get("url", ""), published,
                     score_text(f"{headline}. {summary}"))
        )
    return items


def aggregate_sentiment(items: list[NewsItem]) -> float | None:
    scored = [i.sentiment for i in items if i.sentiment != 0]
    return round(sum(scored) / len(scored), 3) if scored else None
