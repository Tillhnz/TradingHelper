"""Internetstimmung zu einem Wert: Was sagen soziale Netzwerke, wie groß ist die Aufmerksamkeit?

Quellen (alle optional, jede fällt still weg, wenn sie nicht erreichbar ist):
* StockTwits – öffentliche Nachrichtenströme je Kürzel, viele Beiträge sind von den Autoren selbst als „Bullish“
  oder „Bearish“ markiert (vor allem US-Werte und Krypto). Ohne Schlüssel.
* Bluesky – Suche nach $Kürzel bzw. Firmenname. Mit Handle + App-Passwort (Einstellungen → Datenquellen) zuverlässig.
* Reddit – r/wallstreetbets, r/stocks, r/investing, r/mauerstrassenwetten, r/Finanzen, r/aktien. Reddit lässt seit
  Mai 2026 nur noch angemeldete Apps zu: Client-ID und Secret einer eigenen Reddit-App eintragen.
* Wikipedia-Seitenaufrufe – wie viele Menschen sich gerade über das Unternehmen informieren (Aufmerksamkeit im
  Vergleich zum üblichen Niveau). Ohne Schlüssel.

Texte werden mit derselben Stimmungsanalyse bewertet wie die Nachrichten (deutsch und englisch, inkl. gelernter
Korrekturen). Pro Wert entsteht: Stimmung −1…+1, Zahl der Beiträge, Anteil bullisher Stimmen, „Buzz“ (Beiträge der
letzten 24 h gegenüber dem Wochenschnitt) und Aufmerksamkeit (Wikipedia). Ein Tageswert wird gespeichert, damit das
Modell künftig auch daraus lernen kann.
"""

from __future__ import annotations

import logging
import math
import re
import statistics
import threading
import time
from datetime import date, datetime, timedelta, timezone

import requests

from . import gettex, market, marketstore, news

log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "TradeHelper/2.0 (self-hosted; https://github.com/Tillhnz/tradinghelper)"}
TTL = 1800
SUBREDDITS = "wallstreetbets+stocks+investing+mauerstrassenwetten+Finanzen+aktien"
_TOKENS: dict[str, tuple[float, str]] = {}
_LOCK = threading.Lock()


def _ticker_for(symbol: str, info: dict | None) -> str | None:
    """Kürzel, unter dem Social-Plattformen den Wert führen (US-Kürzel bzw. Krypto)."""
    s = symbol.upper()
    if s.endswith("=X") or s.startswith("^") or s.endswith("=F"):
        return None
    if "-" in s and "." not in s:  # Krypto: BTC-EUR → BTC.X (StockTwits)
        return s.split("-")[0] + ".X"
    if gettex.is_gettex(s):
        isin = gettex.isin_of(s)
        t = (info or {}).get("ticker")
        # Nur US-Werte und große Titel mit US-Listing (ADR) haben dort meist dasselbe Kürzel
        return t if t and (isin.startswith("US") or len(t) <= 4) else None
    if "." in s:
        return None  # z. B. SAP.DE: auf StockTwits als SAP (US-Listing) – unklar, lieber auslassen
    return s


def _iso(ts) -> str | None:
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def stocktwits(ticker: str) -> list[dict]:
    r = requests.get(f"https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json", headers=HEADERS, timeout=12)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    out = []
    for m in r.json().get("messages", []):
        label = ((m.get("entities") or {}).get("sentiment") or {}).get("basic")
        out.append({"source": "StockTwits", "text": (m.get("body") or "")[:400], "time": _iso(m.get("created_at")),
                    "label": 1 if label == "Bullish" else -1 if label == "Bearish" else 0,
                    "url": f"https://stocktwits.com/message/{m.get('id')}", "likes": (m.get("likes") or {}).get("total", 0)})
    return out


def _bluesky_token(handle: str, password: str) -> str | None:
    key = "bsky:" + handle
    with _LOCK:
        hit = _TOKENS.get(key)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    r = requests.post("https://bsky.social/xrpc/com.atproto.server.createSession",
                      json={"identifier": handle, "password": password}, headers=HEADERS, timeout=12)
    r.raise_for_status()
    tok = r.json().get("accessJwt")
    with _LOCK:
        _TOKENS[key] = (time.time(), tok)
    return tok


def bluesky(query: str, settings) -> list[dict]:
    headers = dict(HEADERS)
    base = "https://public.api.bsky.app"
    if settings.bluesky_handle and settings.bluesky_app_password:
        tok = _bluesky_token(settings.bluesky_handle, settings.bluesky_app_password)
        if tok:
            headers["Authorization"] = f"Bearer {tok}"
            base = "https://bsky.social"
    r = requests.get(f"{base}/xrpc/app.bsky.feed.searchPosts", params={"q": query, "limit": 50, "sort": "latest"},
                     headers=headers, timeout=12)
    if r.status_code in (401, 403):
        return []
    r.raise_for_status()
    out = []
    for p in r.json().get("posts", []):
        rec = p.get("record") or {}
        uri = p.get("uri", "")
        handle = (p.get("author") or {}).get("handle", "")
        rkey = uri.rsplit("/", 1)[-1]
        out.append({"source": "Bluesky", "text": (rec.get("text") or "")[:400], "time": _iso(rec.get("createdAt")),
                    "label": 0, "url": f"https://bsky.app/profile/{handle}/post/{rkey}" if handle else None,
                    "likes": p.get("likeCount", 0)})
    return out


def _reddit_token(cid: str, secret: str) -> str | None:
    key = "reddit:" + cid
    with _LOCK:
        hit = _TOKENS.get(key)
    if hit and time.time() - hit[0] < 3000:
        return hit[1]
    r = requests.post("https://www.reddit.com/api/v1/access_token", auth=(cid, secret),
                      data={"grant_type": "client_credentials"}, headers=HEADERS, timeout=12)
    r.raise_for_status()
    tok = r.json().get("access_token")
    with _LOCK:
        _TOKENS[key] = (time.time(), tok)
    return tok


def reddit(query: str, settings) -> list[dict]:
    if not (settings.reddit_client_id and settings.reddit_client_secret):
        return []
    tok = _reddit_token(settings.reddit_client_id, settings.reddit_client_secret)
    r = requests.get(f"https://oauth.reddit.com/r/{SUBREDDITS}/search",
                     params={"q": query, "restrict_sr": 1, "sort": "new", "t": "week", "limit": 50},
                     headers={**HEADERS, "Authorization": f"Bearer {tok}"}, timeout=12)
    r.raise_for_status()
    out = []
    for c in (r.json().get("data") or {}).get("children", []):
        d = c.get("data") or {}
        out.append({"source": "Reddit", "text": f"{d.get('title', '')} {d.get('selftext', '')[:300]}".strip(),
                    "time": datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc).isoformat(),
                    "label": 0, "url": f"https://www.reddit.com{d.get('permalink', '')}", "likes": d.get("score", 0),
                    "sub": d.get("subreddit")})
    return out


def wikipedia_attention(name: str) -> dict | None:
    """Seitenaufrufe der letzten Tage im Vergleich zum Median der 60 Tage davor."""
    title = None
    for lang in ("de", "en"):
        try:
            r = requests.get(f"https://{lang}.wikipedia.org/w/api.php", headers=HEADERS, timeout=10,
                             params={"action": "query", "list": "search", "srsearch": name, "format": "json", "srlimit": 1})
            hits = r.json().get("query", {}).get("search", [])
        except (requests.RequestException, ValueError):
            continue
        if hits and name.split()[0].lower() in hits[0]["title"].lower():
            title, project = hits[0]["title"].replace(" ", "_"), f"{lang}.wikipedia"
            break
    if not title:
        return None
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=70)
    url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{project}/all-access/user/"
           f"{requests.utils.quote(title, safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
    r = requests.get(url, headers=HEADERS, timeout=12)
    if not r.ok:
        return None
    views = [int(i.get("views", 0)) for i in r.json().get("items", [])]
    if len(views) < 20:
        return None
    base = statistics.median(views[:-3]) or 1
    recent = sum(views[-3:]) / 3
    return {"title": title.replace("_", " "), "project": project, "recent": round(recent), "usual": round(base),
            "ratio": round(recent / base, 2), "series": views[-30:]}


def score_posts(posts: list[dict]) -> dict:
    """Stimmung, Bull-Anteil und Buzz aus einzelnen Beiträgen."""
    now = datetime.now(timezone.utc)
    scored = []
    for p in posts:
        s = news.score_text(p["text"]) if p.get("text") else 0.0
        if p.get("label"):
            s = 0.6 * p["label"] + 0.4 * s  # eigene Markierung des Autors zählt mehr als die Textanalyse
        w = 1 + math.log1p(max(0, p.get("likes") or 0)) * 0.3
        scored.append((s, w, p))
    if not scored:
        return {"score": None, "n": 0}
    total_w = sum(w for _, w, _ in scored)
    score = sum(s * w for s, w, _ in scored) / total_w if total_w else 0
    bull = sum(1 for s, _, _ in scored if s > 0.15)
    bear = sum(1 for s, _, _ in scored if s < -0.15)
    times = [datetime.fromisoformat(p["time"]) for _, _, p in scored if p.get("time")]
    last24 = sum(1 for t in times if now - t < timedelta(hours=24))
    week = [t for t in times if now - t < timedelta(days=7)]
    span_days = max(1.0, min(7.0, (now - min(week)).total_seconds() / 86400)) if week else 7.0
    per_day = len(week) / span_days if week else 0
    return {"score": round(score, 3), "n": len(scored), "bull": bull, "bear": bear,
            "bull_ratio": round(bull / (bull + bear), 2) if bull + bear else None,
            "last24": last24, "buzz": round(last24 / per_day, 2) if per_day else None}


def collect(symbol: str, settings, name: str | None = None) -> dict:
    info = market.cached_info(symbol) or {}
    name = news.search_name(name or info.get("name"), symbol)
    ticker = _ticker_for(symbol, info)
    posts: list[dict] = []
    sources: dict[str, dict] = {}
    queries = [q for q in ([f"${ticker.split('.')[0]}"] if ticker else []) + ([f'"{name}"'] if name else []) if q]

    def add(src: str, fn):
        try:
            got = fn()
        except Exception as exc:  # noqa: BLE001
            sources[src] = {"error": type(exc).__name__}
            return
        if got:
            sources[src] = score_posts(got)
            posts.extend(got)

    if ticker:
        add("StockTwits", lambda: stocktwits(ticker))
    if queries:
        add("Bluesky", lambda: [p for q in queries[:2] for p in bluesky(q, settings)])
        add("Reddit", lambda: reddit(" OR ".join(queries[:2]), settings))
    attention = None
    if name and not (symbol.startswith("^") or symbol.endswith("=X") or symbol.endswith("=F")):
        try:
            attention = wikipedia_attention(name)
        except Exception as exc:  # noqa: BLE001
            log.debug("Wikipedia-Aufrufe %s: %s", name, exc)
    # doppelte Beiträge (gleicher Text) nur einmal
    seen, uniq = set(), []
    for p in posts:
        k = re.sub(r"\W+", "", (p.get("text") or "").lower())[:120]
        if k and k not in seen:
            seen.add(k)
            uniq.append(p)
    agg = score_posts(uniq)
    samples = sorted(uniq, key=lambda p: p.get("time") or "", reverse=True)[:12]
    for p in samples:
        p["sentiment"] = round(news.score_text(p["text"]), 2) if p.get("text") else 0
    return {"symbol": symbol.upper(), "name": name, "ticker": ticker, **agg, "sources": sources,
            "attention": attention, "samples": samples, "fetched": time.time()}


def get(symbol: str) -> dict | None:
    store = marketstore.get_store()
    return store.get(f"social:{symbol.upper()}") if store else None


def history(symbol: str) -> dict[str, dict]:
    store = marketstore.get_store()
    return (store.get(f"social_hist:{symbol.upper()}") if store else None) or {}


def _skip(symbol: str) -> bool:
    s = symbol.upper()
    return s.startswith("^") or s.endswith("=X") or s.endswith("=F")


def refresh(storage, symbols: list[str], force: bool = False) -> int:
    from . import settings_store
    from .config import settings as base

    if not base.social_enabled:
        return 0
    store = marketstore.get_store()
    if store is None:
        return 0
    cfg = settings_store.for_user(storage, base)
    n = 0
    for sym in symbols:
        if _skip(sym):
            continue
        hit = store.get_with_age(f"social:{sym}")
        if hit and hit[1] < TTL and not force:
            continue
        data = collect(sym, cfg)
        store.put(f"social:{sym}", data)
        if data.get("n") or data.get("attention"):
            hist = history(sym)
            hist[date.today().isoformat()] = {"score": data.get("score"), "n": data.get("n"), "buzz": data.get("buzz"),
                                              "attention": (data.get("attention") or {}).get("ratio")}
            if len(hist) > 800:
                for k in sorted(hist)[:-800]:
                    hist.pop(k, None)
            store.put(f"social_hist:{sym}", hist)
        n += 1
        time.sleep(0.5)  # schonend gegenüber den Plattformen
    return n
