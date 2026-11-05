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

# ---------- Stimmung einer Schlagzeile (regelbasiert, Deutsch und Englisch) ----------
#
# 1. Feste Wendungen zuerst („senkt Kursziel“, „price target raised“, „Inflation steigt“). Was sie abdecken, wird
#    für die Einzelwörter danach nicht mehr gezählt – „senkt Kursziel trotz Kaufempfehlung“ zählt also nicht positiv.
# 2. Nebensätze mit „trotz/despite/obwohl“ zählen nur zu 30 %: Die Hauptaussage steht davor.
# 3. Verneinung kurz vor einem Treffer („nicht“, „kein“, „not“, „no“) dreht ihn um.
# 4. Fragen („Time to Buy?“) und Lockschlagzeilen sind Meinungsmache und zählen nur zu 30 % bzw. gar nicht.
# Ergebnis: Summe / (Betragssumme + 2). Ein einzelnes schwaches Signal ergibt also nur ±0,33, nicht gleich ±1.

_W = r"[\wäöüß-]*"
PHRASES: list[tuple[str, float]] = [
    # Lockschlagzeilen ohne Aussage
    (r"time to buy|should you buy|is it time to|buy (it )?now\?|kaufen oder (nicht|verkaufen)|jetzt kaufen\?", 0),
    # Kursziele und Einstufungen
    (rf"(senkt|senken|reduziert|kappt|kürzt|streicht){_W}( \S+){{0,4}} (kurs)?ziel", -2),
    (r"(kurs)?ziel (für \S+ )?(wird |werden )?(gesenkt|reduziert|gekappt|gekürzt)", -2),
    (r"(cuts?|lowers?|lowered|trims?|trimmed|slash(es|ed)?|reduces?|reduced)( \S+){0,4} (price )?targets?", -2),
    (r"price targets? (cut|lowered|trimmed|reduced|slashed)", -2),
    (rf"(hebt|heben|erhöht|erhöhen|schraubt|schrauben){_W}( \S+){{0,4}} (kurs)?ziel( \S+){{0,4}} (an|hoch|nach oben)\b", 2),
    (rf"(hebt|heben|erhöht|erhöhen){_W}( \S+){{0,4}} (kurs)?ziel", 2),
    (r"(kurs)?ziel (für \S+ )?(wird |werden )?(angehoben|erhöht|hochgesetzt)", 2),
    (r"(raises?|raised|lifts?|lifted|boosts?|boosted|hikes?|hiked|ups)( \S+){0,4} (price )?targets?", 2),
    (r"price targets? (raised|lifted|increased|hiked|boosted)", 2),
    (r"targets? (stays?|remains?|unchanged|bestätigt|unverändert)|(kurs)?ziel (bestätigt|unverändert|bleibt)", 0),
    (r"(herabgestuft|abgestuft|downgrades?|downgraded|downgrading|cut to (sell|underweight|neutral|hold))", -2),
    (r"(hochgestuft|heraufgestuft|upgrades?|upgraded|upgrading|raised to (buy|overweight|outperform))", 2),
    (r"(kaufempfehlung|kaufen-empfehlung|buy rating|outperform|overweight|übergewichten|kaufchance)", 1),
    (r"(verkaufsempfehlung|sell rating|underperform|underweight|untergewichten)", -1),
    # Prognosen und Zahlen
    (r"gewinnwarnung|umsatzwarnung|profit warning", -2),
    (rf"(senkt|kappt|kürzt|reduziert){_W}( \S+){{0,3}} (prognose|ausblick|jahresziele?)|(prognose|ausblick) (gesenkt|gekappt|gekürzt)", -2),
    (r"(cuts?|lowers?|lowered|slashes?|trims?)( \S+){0,2} (guidance|forecast|outlook)", -2),
    (rf"(hebt|erhöht){_W}( \S+){{0,3}} (prognose|ausblick|jahresziele?)|(prognose|ausblick) (angehoben|erhöht)", 2),
    (r"(raises?|raised|lifts?|boosts?)( \S+){0,2} (guidance|forecast|outlook)", 2),
    (r"(beats?|tops?|topped|exceeds?|exceeded|surpass(es|ed)?) (\S+ )?(estimates|expectations|forecasts?|consensus)", 2),
    (r"übertr(ifft|afen?) (die )?(erwartungen|prognosen?|schätzungen)|über (den )?erwartungen", 2),
    (r"(misses|missed|miss|falls? short of|below) (\S+ )?(estimates|expectations|forecasts?|consensus)", -2),
    (r"verfehlt (die )?(erwartungen|prognosen?|schätzungen)|unter (den )?erwartungen|enttäusch\w*", -2),
    # Makro: steigende Inflation/Zinsen/Arbeitslosigkeit sind schlecht, fallende gut
    (r"(inflation|teuerung|zinsen|leitzins|arbeitslosigkeit|arbeitslosenquote|ölpreis|unemployment|yields?|rates)"
     r"( \S+){0,2} (steigt|steigen|klettert|klettern|zieht an|erreicht|rises?|rose|climbs?|jumps?|surges?|hits?)", -1),
    (r"(inflation|teuerung|zinsen|leitzins|arbeitslosigkeit|ölpreis|unemployment|yields?)( \S+){0,2} "
     r"(sinkt|sinken|fällt|fallen|geht zurück|eases?|falls?|fell|drops?|cools?)", 1),
    (r"zinserhöhung|rate hike", -1),
    (r"zinssenkung|rate cut", 1),
]
WORDS: list[tuple[str, float]] = [
    # Kursbewegung
    (r"legt (\S+ ){0,3}zu|zieht an|steigt|steigen|klettert|klettern|springt|springen|erholt|erholung|gewinnt|"
     r"im plus|kaufsignal|bricht aus|ausbruch|rekordhoch|allzeithoch|höchststand|zwei-monatshoch|"
     r"climbs?|rises?|rose|jumps?|surges?|soars?|rall(y|ies)|gains?|rebounds?|record high|all-time high|"
     r"breaks? (through|out)|breakout|higher|bullish", 1),
    (r"fällt|fallen|sinkt|sinken|rutscht|rutschen|bricht ein|stürzt|einbruch|verliert|verlieren|im minus|gibt nach|"
     r"unter druck|minus \d+|verkaufssignal|tiefststand|jahrestief|falls?|fell|drops?|dropped|slides?|slumps?|plunges?|"
     r"tumbles?|sinks?|declines?|sell-?off|crash(es)?|lower|bearish", -1),
    # Geschäft
    (r"rekord\w*|record (revenue|sales|profit|quarter|results)|wachstum|growth|gewinnsprung|gewinnsteigerung|"
     r"großauftrag|auftrag|wins? (a )?(contract|order|deal)|partnerschaft|partnership|kooperation|aktienrückkauf|"
     r"buyback|dividendenerhöhung|dividend (hike|increase)|zulassung|approval|approved|übernahmeangebot|takeover bid|strong|stark", 1),
    (r"verlust\w*|loss(es)?|klage|lawsuit|sued|ermittlung\w*|investigation|probe into|rückruf|recall|stellenabbau|"
     r"layoffs?|job cuts|insolvenz|bankruptcy|betrug|fraud|razzia|streik|strike|lieferproblem\w*|verzögerung\w*|"
     r"delay(s|ed)?|schwach\w*|weak|warnung|warning|sanktion\w*|zölle|tariffs?", -1),
]
_NEGATORS = {"nicht", "kein", "keine", "keinen", "not", "no", "never", "ohne", "without", "kaum"}
_SUBORDINATE = re.compile(r"\b(trotz|despite|obwohl|although|even as|in spite of)\b")
_PHRASES = [(re.compile(rf"\b(?:{p})"), w) for p, w in PHRASES]
_WORDS = [(re.compile(rf"\b(?:{p})\b"), w) for p, w in WORDS]


def _clause_score(t: str) -> tuple[float, float]:
    """(Summe, Betragssumme) eines Satzteils."""
    used = [False] * len(t)
    total = weight = 0.0

    def free(m) -> bool:
        return not any(used[m.start():m.end()])

    def take(m, w):
        nonlocal total, weight
        for i in range(m.start(), m.end()):
            used[i] = True
        before = re.findall(r"[\wäöüß]+", t[max(0, m.start() - 25):m.start()])[-3:]
        if w and any(b in _NEGATORS for b in before):
            w = -w
        total += w
        weight += abs(w)

    for rx, w in _PHRASES:
        for m in rx.finditer(t):
            if free(m):
                take(m, w)
    for rx, w in _WORDS:
        for m in rx.finditer(t):
            if free(m):
                take(m, w)
    return total, weight


def score_text(text: str) -> float:
    """Stimmung einer Meldung zwischen −1 und +1."""
    t = " ".join((text or "").lower().replace("’", "'").split())
    if not t:
        return 0.0
    head = t.split(". ", 1)[0]
    question = head.rstrip().endswith("?")
    total = weight = 0.0
    # Hauptsatz und Nebensatz mit „trotz/despite“ getrennt bewerten
    parts = _SUBORDINATE.split(t, maxsplit=1)
    main = parts[0]
    s, w = _clause_score(main)
    total, weight = s, w
    if len(parts) == 3:
        rest = parts[2]
        # Der Nebensatz reicht bis zum nächsten Satzzeichen, danach geht es normal weiter
        sub, _, after = re.split(r"([,;:.!?–-] )", rest, maxsplit=1) + ["", ""] if re.search(r"[,;:.!?–-] ", rest) else (rest, "", "")
        s2, w2 = _clause_score(sub)
        total += 0.3 * s2
        weight += 0.3 * w2
        if after:
            s3, w3 = _clause_score(after)
            total += s3
            weight += w3
    if question:
        total *= 0.3
    return round(max(-1.0, min(1.0, total / (weight + 2))), 3) if weight else 0.0


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


# Kursseiten, Optionsscheine und ähnliche Treffer ohne Nachrichtenwert
_JUNK = re.compile(
    r"\b[A-Z]{1,6}\d{6}[CP]\d{8}\b|interactive stock chart|stock price,? news|stock quote|quote (&|and) history"
    r"|price history|kurs,? (news|chart)|aktienkurs (und|&) |realtime-kurs|kurs (&|und) chart",
    re.I,
)


def _relevant(items: list[NewsItem], term: str, in_summary: bool = False) -> list[NewsItem]:
    """Suchtreffer nennen den Namen oft nur am Rand: Schlagzeile (bei Yahoo auch Anreißer) muss ihn enthalten."""
    words = [w for w in re.findall(r"\w+", term.lower()) if len(w) > 1] or [term.lower()]
    first = words[0]
    return [i for i in items
            if first in (f"{i.headline} {i.summary}" if in_summary else i.headline).lower() and not _JUNK.search(i.headline)]


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
        yterm = term or symbol.split(".")[0]
        tasks.append(lambda: _relevant(fetch_feed(yahoo_url(symbol), "Yahoo Finance"), yterm, in_summary=True))
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
