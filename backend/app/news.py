"""Nachrichten aus mehreren Quellen plus regelbasiertes Sentiment (ohne LLM).

Pro Wert: Google News (deutsch und englisch, Suche nach dem Firmennamen), Yahoo Finance (RSS, nur Yahoo-Ticker)
und Finnhub (mit Schlüssel). Für die Startseite: frei einstellbare RSS-/Atom-Feeds. Alles wird zusammengeführt,
doppelte Schlagzeilen fliegen raus, sortiert wird nach Zeit.
"""

from __future__ import annotations

import html
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import requests

log = logging.getLogger(__name__)

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
    via: str = ""  # über welche Quelle die Meldung kam (Google News, Yahoo, Finnhub, Feedname)

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


_LOOKUP: dict[str, str | None] = {}


def _lookup_isin(isin: str, api_key: str) -> str | None:
    """Finnhub-Ticker zu einer ISIN (für gettex-Werte, die über die ISIN geführt werden)."""
    if isin in _LOOKUP:
        return _LOOKUP[isin]
    sym = None
    try:
        r = requests.get(f"{FINNHUB_URL}/search", params={"q": isin, "token": api_key}, timeout=15)
        r.raise_for_status()
        res = [x for x in r.json().get("result", []) if x.get("symbol")]
        plain = [x for x in res if "." not in x["symbol"]]  # US-Ticker bevorzugen, dort gibt es die meisten News
        pick = (plain or res or [None])[0]
        sym = pick["symbol"] if pick else None
    except (requests.RequestException, ValueError):
        return None
    _LOOKUP[isin] = sym
    return sym


def fetch_news(symbol: str, api_key: str, lookback_days: int = 3, limit: int = 10) -> list[NewsItem]:
    if not api_key:
        return []
    if symbol.upper().endswith(".GTX"):
        resolved = _lookup_isin(symbol.upper()[:-4], api_key)
        if not resolved:
            return []
        symbol = resolved
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
                     score_text(f"{headline}. {summary}"), "Finnhub")
        )
    return items


# ---------- RSS / Atom ----------

MAX_BYTES = 2_000_000
CACHE_TTL = 600
_CACHE: dict[str, tuple[float, list[NewsItem]]] = {}
_CACHE_LOCK = threading.Lock()
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TradeHelper/1.0; +https://github.com/Tillhnz/tradinghelper)",
           "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"}
_TAG = re.compile(r"<[^>]+>")


def _clean(text: str | None, limit: int = 400) -> str:
    t = html.unescape(_TAG.sub(" ", text or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= limit else t[: limit - 1].rsplit(" ", 1)[0] + " …"


def _date(text: str | None) -> str:
    if not text:
        return ""
    text = text.strip()
    try:
        d = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child(el, name: str):
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _text(el, name: str) -> str:
    c = _child(el, name)
    return (c.text or "").strip() if c is not None else ""


def parse_feed(content: bytes, via: str = "", split_source: bool = False) -> list[NewsItem]:
    """RSS 2.0 und Atom. split_source: Google-Titel enden auf " - Quelle", das wird abgetrennt."""
    if b"<!ENTITY" in content[:5000]:  # keine Entity-Definitionen (Schutz vor XML-Bomben)
        return []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    out: list[NewsItem] = []
    for el in root.iter():
        kind = _local(el.tag)
        if kind not in ("item", "entry"):
            continue
        title = _clean(_text(el, "title"), 300)
        if not title:
            continue
        if kind == "item":
            url = _text(el, "link")
            published = _date(_text(el, "pubdate") or _text(el, "date"))
            summary = _text(el, "description")
        else:
            link = _child(el, "link")
            url = (link.get("href") or link.text or "").strip() if link is not None else ""
            published = _date(_text(el, "published") or _text(el, "updated"))
            summary = _text(el, "summary") or _text(el, "content")
        source = _text(el, "source") or via
        if split_source and " - " in title:
            head, tail = title.rsplit(" - ", 1)
            if len(tail) <= 60:
                title, source = head.strip(), (_text(el, "source") or tail.strip())
        summary = "" if split_source else _clean(summary)  # Google-Beschreibungen sind nur Linklisten
        if summary.lower().startswith(title.lower()[:40]):
            summary = summary[len(title):].strip(" .-–") if len(summary) > len(title) else ""
        out.append(NewsItem(title, summary, source, url, published, score_text(f"{title}. {summary}"), via))
    return out


def fetch_feed(url: str, via: str = "", split_source: bool = False) -> list[NewsItem]:
    """Lädt einen Feed (mit 10-Minuten-Cache). Fehler ergeben eine leere Liste."""
    now = time.time()
    with _CACHE_LOCK:
        hit = _CACHE.get(url)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]
    items: list[NewsItem] = []
    try:
        with requests.get(url, headers=HEADERS, timeout=12, stream=True) as r:
            r.raise_for_status()
            chunks, size = [], 0
            for chunk in r.iter_content(65536):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError("Feed zu groß")
                chunks.append(chunk)
        items = parse_feed(b"".join(chunks), via, split_source)
    except (requests.RequestException, ValueError) as exc:
        log.info("Feed %s nicht lesbar: %s", url, exc)
    with _CACHE_LOCK:
        if len(_CACHE) > 500:
            _CACHE.clear()
        _CACHE[url] = (now, items)
    return items


def parse_feed_list(text: str) -> list[tuple[str, str]]:
    """'Name | URL' je Zeile -> [(Name, URL)]. Ohne Name wird der Host genommen."""
    out = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        name, _, url = ln.rpartition("|") if "|" in ln else ("", "", ln)
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            continue
        name = name.strip() or re.sub(r"^www\.", "", url.split("/")[2])
        out.append((name, url))
    return out


# ---------- Zusammenführen ----------

def _key(headline: str) -> str:
    return re.sub(r"[^a-z0-9äöüß]+", "", headline.lower())[:70]


def merge(groups: list[list[NewsItem]], lookback_days: int | None = None, limit: int = 20) -> list[NewsItem]:
    """Doppelte Schlagzeilen entfernen, nach Zeit sortieren (neueste zuerst), Zeitfenster anwenden."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat() if lookback_days else ""
    seen: dict[str, NewsItem] = {}
    for group in groups:
        for it in group:
            if cutoff and it.published and it.published < cutoff:
                continue
            k = _key(it.headline)
            if not k:
                continue
            old = seen.get(k)
            if old is None or (not old.summary and it.summary):
                seen[k] = it
    return sorted(seen.values(), key=lambda i: i.published or "", reverse=True)[:limit]


_SUFFIX = re.compile(
    r"[\s,]+(se|ag|aktiengesellschaft|kgaa|gmbh|inc\.?|corp\.?|corporation|co\.?|ltd\.?|plc|n\.?v\.?|s\.?a\.?|asa|ab|oyj|spa|"
    r"holding|holdings|group|& co\.?|class [a-c]|reg\.?|vz\.?|st\.?|namens-aktien|inhaber-aktien|o\.n\.?)$",
    re.I,
)


def search_name(name: str | None, symbol: str = "") -> str:
    """Firmenname ohne Rechtsform für die Nachrichtensuche ("SAP SE" -> "SAP")."""
    n = (name or "").strip()
    if not n:
        base = symbol.split(".")[0]
        return "" if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", base) else base.replace("-", " ")
    n = re.sub(r"\(.*?\)", "", n)
    n = re.split(r"\s+UCITS\b", n, flags=re.I)[0]  # ETFs: "iShares Core MSCI World UCITS ETF USD" -> Fondsname
    n = re.sub(r"\s+(ETF|EUR|USD|GBP|CHF)$", "", n.strip(), flags=re.I)
    for _ in range(3):
        n2 = _SUFFIX.sub("", n).strip(" ,.-")
        if n2 == n:
            break
        n = n2
    return n


def google_url(query: str, lang: str = "de") -> str:
    region = ("de", "DE", "DE:de") if lang == "de" else ("en-US", "US", "US:en")
    return (f"https://news.google.com/rss/search?q={quote_plus(query)}"
            f"&hl={region[0]}&gl={region[1]}&ceid={region[2]}")


def yahoo_url(symbol: str) -> str:
    return f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote_plus(symbol)}&region=US&lang=en-US"


def is_yahoo_symbol(symbol: str) -> bool:
    return not symbol.upper().endswith(".GTX")


def _relevant(items: list[NewsItem], term: str) -> list[NewsItem]:
    """Google findet auch Meldungen, die den Namen nur am Rand nennen; Schlagzeile muss ihn enthalten."""
    words = [w for w in re.findall(r"\w+", term.lower()) if len(w) > 2] or [term.lower()]
    first = words[0]
    return [i for i in items if first in i.headline.lower()]


def collect(symbol: str, settings, name: str | None = None, limit: int = 12) -> list[NewsItem]:
    """Alle eingeschalteten Quellen für einen Wert, zusammengeführt."""
    days = max(1, int(getattr(settings, "news_lookback_days", 3) or 3))
    tasks = []
    term = search_name(name, symbol)
    if getattr(settings, "news_google", True) and term:
        q = f'"{term}" when:{days}d'
        tasks.append(lambda: _relevant(fetch_feed(google_url(f"{q} Aktie", "de"), "Google News", True), term))
        tasks.append(lambda: _relevant(fetch_feed(google_url(f"{q} stock", "en"), "Google News", True), term))
    if getattr(settings, "news_yahoo", True) and is_yahoo_symbol(symbol) and not symbol.startswith("^"):
        tasks.append(lambda: fetch_feed(yahoo_url(symbol), "Yahoo Finance"))
    key = getattr(settings, "finnhub_api_key", "")
    if key:
        tasks.append(lambda: fetch_news(symbol, key, days, limit=limit))
    if not tasks:
        return []
    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        groups = list(pool.map(lambda f: _safe(f), tasks))
    return merge(groups, days, limit)


def _safe(fn) -> list[NewsItem]:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - eine kaputte Quelle darf die anderen nicht stören
        log.warning("Nachrichtenquelle fehlgeschlagen: %s", exc)
        return []


def market_news(settings, limit: int = 40) -> list[NewsItem]:
    """Allgemeine Markt- und Wirtschaftsnachrichten aus den eingestellten Feeds."""
    feeds = parse_feed_list(getattr(settings, "news_feeds", ""))
    if not feeds:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(feeds))) as pool:
        groups = list(pool.map(lambda f: _safe(lambda: fetch_feed(f[1], f[0])), feeds))
    # Jede Quelle soll zu Wort kommen: pro Feed höchstens 8 Meldungen, dann nach Zeit mischen.
    groups = [sorted(g, key=lambda i: i.published or "", reverse=True)[:8] for g in groups]
    return merge(groups, 3, limit)


def sources(settings) -> list[str]:
    out = []
    if getattr(settings, "news_google", True):
        out.append("Google News")
    if getattr(settings, "news_yahoo", True):
        out.append("Yahoo Finance")
    if getattr(settings, "finnhub_api_key", ""):
        out.append("Finnhub")
    return out


def aggregate_sentiment(items: list[NewsItem]) -> float | None:
    scored = [i.sentiment for i in items if i.sentiment != 0]
    return round(sum(scored) / len(scored), 3) if scored else None
