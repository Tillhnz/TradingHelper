"""Unternehmens- und Fondskennzahlen mit Kurzbeschreibung für die Seite eines Werts.

Quellen:
- onvista (gleiche Schnittstelle wie die gettex-Kurse): Kennzahlen je Geschäftsjahr für Aktien, Stammdaten,
  Kosten, Positionen und Beschreibung für ETFs/Fonds.
- Wikipedia (deutsch): Kurzbeschreibung eines Unternehmens.
- Yahoo (yfinance) als Rückfall für Werte ohne ISIN (US-Kürzel, Krypto) – Beschreibung dort auf Englisch.
Alles wird 12 Stunden zwischengespeichert; Kennzahlen ändern sich höchstens ein paarmal im Jahr.
"""
from __future__ import annotations

import html
import logging
import re
import time

import requests

from . import gettex

log = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 12 * 3600
HEADERS = {"User-Agent": "TradeHelper/1.0 (self-hosted; https://github.com/Tillhnz/tradinghelper)", "Accept": "application/json"}
ONVISTA = gettex.BASE


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _r(v, digits=2):
    x = _num(v)
    return round(x, digits) if x is not None else None


def _text(parts) -> str:
    """onvista liefert Absätze als Liste mit HTML – in schlichten Text umwandeln."""
    if isinstance(parts, str):
        parts = [{"value": parts}]
    out = []
    for p in parts or []:
        if p.get("type") == "NewsSubHeadline":
            continue
        t = re.sub(r"<[^>]+>", "", str(p.get("value") or ""))
        t = html.unescape(re.sub(r"\s+", " ", t)).strip()
        if t:
            out.append(t)
    return "\n\n".join(out)


def _short(text: str, limit: int = 700) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[: end + 1] if end > limit * 0.4 else cut.rstrip() + " …").strip()


def _onvista(kind: str, isin: str) -> dict | None:
    # /instruments/{STOCK|FUND}/… statt /stocks|funds/… – den alten Pfad bremst onvista mit 429
    typ = {"stocks": "STOCK", "funds": "FUND"}[kind]
    try:
        r = requests.get(f"{ONVISTA}/instruments/{typ}/ISIN:{isin}/snapshot", headers=HEADERS, timeout=15)
    except requests.RequestException as exc:
        log.info("onvista %s %s: %s", kind, isin, exc)
        return None
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    return data if data.get("instrument") else None


def wikipedia(name: str) -> dict | None:
    """Erster passender Artikel der deutschen Wikipedia: Kurzbeschreibung, Einleitung, Link."""
    if not name:
        return None
    q = re.sub(r"\b(SE|AG|Inc\.?|Corp\.?|plc|N\.V\.|S\.A\.|Ltd\.?|Co\.?|KGaA|& Co\.?|Holding|Group)\b", "", name).strip(" ,.-")
    try:
        r = requests.get("https://de.wikipedia.org/w/api.php", headers=HEADERS, timeout=10, params={
            "action": "query", "list": "search", "srsearch": q or name, "format": "json", "srlimit": 3})
        hits = r.json().get("query", {}).get("search", [])
        if not hits:
            return None
        first = (q or name).split()[0].lower()
        hit = next((h for h in hits if first in h["title"].lower()), None)
        if not hit:
            return None
        s = requests.get(f"https://de.wikipedia.org/api/rest_v1/page/summary/{hit['title'].replace(' ', '_')}",
                         headers=HEADERS, timeout=10).json()
    except (requests.RequestException, ValueError) as exc:
        log.info("Wikipedia %s: %s", name, exc)
        return None
    if s.get("type") == "disambiguation" or not s.get("extract"):
        return None
    return {"text": _short(s["extract"]), "tagline": s.get("description"), "source": "Wikipedia",
            "url": (s.get("content_urls") or {}).get("desktop", {}).get("page")}


def _actual(rows: list[dict]) -> tuple[dict, dict]:
    """Letztes abgeschlossenes Geschäftsjahr und Schätzung fürs laufende Jahr (Label mit „e“)."""
    done = [r for r in rows if not str(r.get("label", "")).endswith("e")]
    est = [r for r in rows if str(r.get("label", "")).endswith("e")]
    return (done[-1] if done else {}), (est[0] if est else {})


def _stock(snap: dict) -> dict:
    comp = snap.get("company") or {}
    branch = comp.get("branch") or {}
    fund_done, fund_est = _actual((snap.get("stocksCnFundamentalList") or {}).get("list") or [])
    fin_done, fin_est = _actual((snap.get("stocksCnFinancialList") or {}).get("list") or [])
    bs = [b for b in (snap.get("stocksBalanceSheetList") or {}).get("list") or [] if not b.get("rowEmpty")]
    last = bs[-1] if bs else {}
    prev = bs[-2] if len(bs) > 1 else {}
    ccy = last.get("isoCurrency") or fund_done.get("isoCurrency") or "EUR"
    growth = None
    if _num(last.get("turnover")) and _num(prev.get("turnover")):
        growth = round((last["turnover"] / prev["turnover"] - 1) * 100, 1)
    year = fund_done.get("label") or last.get("label")
    est_year = fund_est.get("label", "").rstrip("e")
    figures = {
        "market_cap": _r(fin_est.get("cnMarketCap") or fin_done.get("cnMarketCap") or fund_done.get("cnMarketCap"), 0),
        "pe": _r(fund_done.get("cnPer"), 1),
        "pe_est": _r(fund_est.get("cnPer"), 1),
        "peg": _r(fund_done.get("cnPeg"), 2),
        "pb": _r(fund_done.get("cnPriceBookvalue"), 1),
        "div_yield": _r(fund_est.get("cnDivYield") or fund_done.get("cnDivYield"), 2),
        "dps": _r(fund_done.get("cnDps"), 2),
        "ex_dividend": (fund_done.get("dateExDividend") or "")[:10] or None,
        "revenue": _r(last.get("turnover"), 0),
        "revenue_growth": growth,
        "net_income": _r(last.get("earningsAfterTax"), 0),
        "eps": _r(last.get("eps") or fin_done.get("cnEpsAdj"), 2),
        "eps_est": _r(fin_est.get("cnEpsAdj"), 2),
        "ebit_margin": _r(fin_done.get("cnEbitMa"), 1),
        "net_margin": _r(fin_done.get("cnMarginNet"), 1),
        "roe": _r(fin_done.get("cnReturnEquity"), 1),
        "equity_ratio": _r(fin_done.get("cnEquityRatio"), 1),
        "employees": int(last["employees"]) if _num(last.get("employees")) else (
            int(fund_done["employees"]) if _num(fund_done.get("employees")) else None),
        "free_float": _r(fund_done.get("cnFreeFloat"), 1),
    }
    return {
        "kind": "stock", "name": comp.get("name") or (snap.get("instrument") or {}).get("name"),
        "sector": (branch.get("sector") or {}).get("name"), "industry": branch.get("name"), "country": comp.get("nameCountry"),
        "currency": ccy, "year": year, "est_year": est_year or None,
        "figures": {k: v for k, v in figures.items() if v is not None},
        "figures_source": "onvista",
    }


def _fund(snap: dict) -> dict:
    det = snap.get("fundsDetails") or {}
    base = snap.get("fundsBaseData") or {}
    issuer = snap.get("fundsIssuer") or {}
    ev = snap.get("fundsEvaluation") or {}
    perf = {p.get("timeSpan"): _r(p.get("performanceTimeSpanPct"), 1) for p in (snap.get("fundsPerformanceList") or {}).get("list") or []}
    risk = {p.get("timeSpan"): p for p in (snap.get("fundsRiskList") or {}).get("list") or []}
    holdings = [{"name": (h.get("instrument") or {}).get("name"), "isin": (h.get("instrument") or {}).get("isin"),
                 "pct": _r(h.get("investmentPct"), 2)} for h in ((snap.get("fundsHoldingList") or {}).get("list") or [])[:8]]
    branches = [{"name": b.get("nameBreakdown"), "pct": _r(b.get("investmentPct"), 1)}
                for b in ((snap.get("branchFundsBreakdownList") or {}).get("list") or [])[:6]]
    bench = ((snap.get("fundsBenchmarkList") or {}).get("list") or [{}])[0].get("instrument", {}).get("name")
    figures = {
        "ter": _r(base.get("ongoingCharges"), 2),
        "volume": _r(base.get("volumeFundEuro"), 0),
        "inception": (base.get("dateEmission") or "")[:10] or None,
        "distribution": (det.get("fundsTypeCapitalisation") or {}).get("name"),
        "replication": (det.get("fundsTypeReplication") or {}).get("name"),
        "region": (det.get("fundsInvestmentRegion") or {}).get("name"),
        "focus": det.get("nameInvestmentFocus"),
        "benchmark": bench,
        "domicile": base.get("nameCountry"),
        "fund_currency": base.get("isoCurrencyFund"),
        "risk_class": ev.get("riskClass"),
        "morningstar": _num(ev.get("morningstarRating")),
        "perf_1y": perf.get("1Y"), "perf_3y": perf.get("3Y"), "perf_5y": perf.get("5Y"),
        "volatility_1y": _r((risk.get("1Y") or {}).get("volatility"), 1),
        "max_drawdown_1y": _r((risk.get("1Y") or {}).get("maxDrawdown"), 1),
    }
    desc = _text(snap.get("background"))
    return {
        "kind": "fund", "name": (snap.get("instrument") or {}).get("name"), "issuer": issuer.get("nameGroupIssuer") or issuer.get("name"),
        "type": det.get("nameTypeFund"), "currency": "EUR",
        "figures": {k: v for k, v in figures.items() if v is not None},
        "holdings": [h for h in holdings if h["name"]], "branches": [b for b in branches if b["name"]],
        "description": {"text": _short(desc), "source": "onvista / Fondsanbieter"} if desc else None,
        "figures_source": "onvista",
    }


def _yahoo(symbol: str) -> dict | None:
    try:
        import yfinance as yf

        info = yf.Ticker(symbol).info or {}
    except Exception as exc:  # noqa: BLE001
        log.info("yfinance info %s: %s", symbol, exc)
        return None
    if not info:
        return None
    figures = {
        "market_cap": _r(info.get("marketCap"), 0),
        "pe": _r(info.get("trailingPE"), 1), "pe_est": _r(info.get("forwardPE"), 1),
        "pb": _r(info.get("priceToBook"), 1),
        "div_yield": _r(info.get("dividendYield"), 2),
        "revenue": _r(info.get("totalRevenue"), 0),
        "revenue_growth": _r((info.get("revenueGrowth") or 0) * 100, 1) if info.get("revenueGrowth") is not None else None,
        "net_margin": _r((info.get("profitMargins") or 0) * 100, 1) if info.get("profitMargins") is not None else None,
        "roe": _r((info.get("returnOnEquity") or 0) * 100, 1) if info.get("returnOnEquity") is not None else None,
        "eps": _r(info.get("trailingEps"), 2), "eps_est": _r(info.get("forwardEps"), 2),
        "employees": info.get("fullTimeEmployees"),
        "beta": _r(info.get("beta"), 2),
    }
    desc = info.get("longBusinessSummary") or info.get("description")
    return {
        "kind": "fund" if info.get("quoteType") in ("ETF", "MUTUALFUND") else "crypto" if info.get("quoteType") == "CRYPTOCURRENCY" else "stock",
        "name": info.get("longName") or info.get("shortName"), "sector": info.get("sector"), "industry": info.get("industry"),
        "country": info.get("country"), "currency": info.get("financialCurrency") or info.get("currency"),
        "figures": {k: v for k, v in figures.items() if v is not None},
        "description": {"text": _short(desc), "source": "Yahoo Finance (englisch)"} if desc else None,
        "figures_source": "Yahoo Finance",
    }


def get(symbol: str, name: str | None = None) -> dict:
    """Kennzahlen und Beschreibung eines Werts; {"kind": None} wenn nichts zu finden ist."""
    key = symbol.upper()
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    out: dict | None = None
    if gettex.is_gettex(key):
        isin = gettex.isin_of(key)
        snap = _onvista("stocks", isin)
        if snap:
            out = _stock(snap)
            out["description"] = wikipedia(out.get("name") or name or "")
        else:
            snap = _onvista("funds", isin)
            if snap:
                out = _fund(snap)
    else:
        out = _yahoo(key)
        if out and out.get("kind") == "stock":
            wiki = wikipedia(out.get("name") or name or "")
            if wiki:
                out["description"] = wiki
    out = out or {"kind": None}
    _CACHE[key] = (time.time(), out)
    return out
