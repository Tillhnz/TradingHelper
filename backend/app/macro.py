"""Volkswirtschaftliche Zahlen und Marktumfeld – ohne API-Schlüssel.

Quellen:
* EZB Data Portal: Einlagezins, Inflation Euroraum und Deutschland (HVPI)
* Eurostat: Arbeitslosigkeit, BIP-Wachstum, Wirtschaftsstimmung (ESI) für Deutschland und den Euroraum
* FRED (St. Louis Fed, CSV ohne Schlüssel): US-Leitzins, Inflation, Arbeitslosigkeit, Zinskurve, Risikoaufschläge,
  Verbraucherstimmung
* Weltbank: Wachstum und Inflation weltweit, USA, China, Deutschland (jährlich)
* Märkte über den Kursspeicher: Indizes, VIX, Zinsen, Dollar, Öl, Gold, Kupfer und die elf US-Branchen-ETFs

Alles wird alle 6 Stunden geholt und im Speicher abgelegt. Für das Modell gibt es „point in time“-Werte: Eine
Monatszahl ist erst nach ihrer üblichen Veröffentlichung bekannt (Verzögerung je Reihe), damit das Modell nicht mit
Zahlen lernt, die es damals noch gar nicht gab.
"""

from __future__ import annotations

import csv
import io
import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
import requests

from . import marketstore

log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TradeHelper/2.0; +https://github.com/Tillhnz/tradinghelper)",
           "Accept": "application/json, text/csv, */*"}
TTL = 6 * 3600

ECB = "https://data-api.ecb.europa.eu/service/data/{flow}/{key}?format=csvdata&startPeriod={start}"
EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{ds}?format=JSON&lang=EN&{q}"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
WORLDBANK = "https://api.worldbank.org/v2/country/{c}/indicator/{ind}?format=json&per_page=60"


@dataclass(frozen=True)
class Series:
    id: str
    label: str
    region: str
    unit: str
    source: str
    ref: str               # Quelle-spezifische Kennung
    lag_days: int          # wie lange nach dem Stichtag die Zahl bekannt ist
    good: int = 0          # +1: steigend ist gut für Aktien, −1: fallend ist gut, 0: neutral
    yoy: bool = False      # aus einem Index die Veränderung zum Vorjahr rechnen
    group: str = "Konjunktur"


SERIES: list[Series] = [
    Series("ecb_rate", "EZB-Einlagezins", "Euroraum", "%", "ecb", "FM|D.U2.EUR.4F.KR.DFR.LEV", 1, -1, group="Zinsen"),
    Series("ea_inflation", "Inflation", "Euroraum", "%", "ecb", "ICP|M.U2.N.000000.4.ANR", 20, -1, group="Preise"),
    Series("de_inflation", "Inflation", "Deutschland", "%", "ecb", "ICP|M.DE.N.000000.4.ANR", 20, -1, group="Preise"),
    Series("de_unemployment", "Arbeitslosenquote", "Deutschland", "%", "eurostat",
           "une_rt_m|geo=DE&age=TOTAL&sex=T&unit=PC_ACT&s_adj=SA", 35, -1),
    Series("ea_unemployment", "Arbeitslosenquote", "Euroraum", "%", "eurostat",
           "une_rt_m|geo=EA20&age=TOTAL&sex=T&unit=PC_ACT&s_adj=SA", 35, -1),
    Series("de_gdp", "BIP-Wachstum (Quartal)", "Deutschland", "%", "eurostat",
           "namq_10_gdp|geo=DE&unit=CLV_PCH_PRE&s_adj=SCA&na_item=B1GQ", 60, 1),
    Series("ea_gdp", "BIP-Wachstum (Quartal)", "Euroraum", "%", "eurostat",
           "namq_10_gdp|geo=EA20&unit=CLV_PCH_PRE&s_adj=SCA&na_item=B1GQ", 60, 1),
    Series("ea_sentiment", "Wirtschaftsstimmung (ESI)", "Euroraum", "Pkt.", "eurostat",
           "ei_bssi_m_r2|geo=EA20&indic=BS-ESI-I&s_adj=SA", 3, 1, group="Stimmung"),
    Series("de_sentiment", "Wirtschaftsstimmung (ESI)", "Deutschland", "Pkt.", "eurostat",
           "ei_bssi_m_r2|geo=DE&indic=BS-ESI-I&s_adj=SA", 3, 1, group="Stimmung"),
    Series("us_rate", "Fed-Leitzins", "USA", "%", "fred", "FEDFUNDS", 3, -1, group="Zinsen"),
    Series("us_inflation", "Inflation", "USA", "%", "fred", "CPIAUCSL", 45, -1, yoy=True, group="Preise"),
    Series("us_unemployment", "Arbeitslosenquote", "USA", "%", "fred", "UNRATE", 10, -1),
    Series("us_curve", "Zinskurve 10J–2J", "USA", "%-Pkt.", "fred", "T10Y2Y", 1, 1, group="Zinsen"),
    Series("us_credit", "Risikoaufschlag Hochzins", "USA", "%-Pkt.", "fred", "BAMLH0A0HYM2", 1, -1, group="Risiko"),
    Series("us_sentiment", "Verbraucherstimmung", "USA", "Pkt.", "fred", "UMCSENT", 20, 1, group="Stimmung"),
    Series("us_claims", "Erstanträge Arbeitslosenhilfe", "USA", "Tsd.", "fred", "ICSA", 5, -1),
    Series("world_gdp", "Wirtschaftswachstum (Jahr)", "Welt", "%", "worldbank", "WLD|NY.GDP.MKTP.KD.ZG", 150, 1),
    Series("cn_gdp", "Wirtschaftswachstum (Jahr)", "China", "%", "worldbank", "CHN|NY.GDP.MKTP.KD.ZG", 150, 1),
    Series("world_inflation", "Inflation (Jahr)", "Welt", "%", "worldbank", "WLD|FP.CPI.TOTL.ZG", 150, -1, group="Preise"),
]
BY_ID = {s.id: s for s in SERIES}

# Startseite „Märkte“ (laufende Kurse) und zusätzliche Reihen fürs Modell (nur Tageskerzen)
MARKETS = [("^GDAXI", "DAX"), ("^STOXX50E", "Euro Stoxx 50"), ("^GSPC", "S&P 500"), ("^IXIC", "Nasdaq"),
           ("^N225", "Nikkei 225"), ("^VIX", "VIX (Angst)"), ("EURUSD=X", "EUR/USD"), ("GC=F", "Gold"),
           ("CL=F", "Öl (WTI)"), ("BTC-EUR", "Bitcoin"), ("^TNX", "US-Rendite 10 J.")]
MARKET_SYMBOLS = [s for s, _ in MARKETS]
SECTOR_ETFS = {"Technologie": "XLK", "Finanzen": "XLF", "Gesundheit": "XLV", "Energie": "XLE", "Industrie": "XLI",
               "Zyklischer Konsum": "XLY", "Basiskonsum": "XLP", "Versorger": "XLU", "Grundstoffe": "XLB",
               "Immobilien": "XLRE", "Kommunikation": "XLC"}
MODEL_SYMBOLS = ["^GSPC", "^GDAXI", "^VIX", "^TNX", "DX-Y.NYB", "CL=F", "GC=F", "HG=F", *SECTOR_ETFS.values()]

# Branchen aus onvista (deutsch) und Yahoo (englisch) → Branchen-ETF
SECTOR_WORDS = [
    ("XLK", ("technolog", "software", "halbleiter", "semiconductor", "it-", "informationstechn", "hardware", "elektronik")),
    ("XLF", ("financ", "finanz", "bank", "versicher", "insurance", "capital markets")),
    ("XLV", ("health", "gesundheit", "pharma", "biotech", "medizin", "medical")),
    ("XLE", ("energy", "energie", "öl", "oil", "gas")),
    ("XLU", ("utilit", "versorger", "strom")),
    ("XLRE", ("real estate", "immobil", "reit")),
    ("XLB", ("material", "chemie", "chemical", "rohstoff", "grundstoff", "stahl", "metal", "mining", "bergbau")),
    ("XLC", ("communication", "telekom", "telecom", "medien", "media", "internet")),
    ("XLP", ("consumer defensive", "basiskonsum", "nahrung", "food", "getränk", "beverage", "haushalt")),
    ("XLY", ("consumer cyclical", "konsum", "auto", "retail", "einzelhandel", "luxus", "reise", "travel")),
    ("XLI", ("industr", "maschinenbau", "luftfahrt", "aerospace", "transport", "logistik", "bau")),
]


def sector_etf(sector: str | None, industry: str | None = None) -> str | None:
    text = f"{sector or ''} {industry or ''}".lower()
    if not text.strip():
        return None
    for etf, words in SECTOR_WORDS:
        if any(w in text for w in words):
            return etf
    return None


# ---------- Abruf und Auswertung der Quellen ----------

def _get(url: str, timeout: float = 20) -> requests.Response:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r


def parse_ecb_csv(text: str) -> list[tuple[str, float]]:
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        t, v = row.get("TIME_PERIOD"), row.get("OBS_VALUE")
        try:
            out.append((_period_day(t), float(v)))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def parse_eurostat(js: dict) -> list[tuple[str, float]]:
    """JSON-stat 2.0: alle Dimensionen außer der Zeit sind durch die Abfrage auf einen Wert festgelegt."""
    ids, sizes = js.get("id") or [], js.get("size") or []
    if "time" not in ids:
        return []
    ti = ids.index("time")
    stride = int(np.prod(sizes[ti + 1:])) if ti + 1 < len(sizes) else 1
    index = js["dimension"]["time"]["category"]["index"]
    values = js.get("value") or {}
    out = []
    for label, pos in index.items():
        v = values.get(str(pos * stride)) if isinstance(values, dict) else (values[pos * stride] if pos * stride < len(values) else None)
        if v is None:
            continue
        out.append((_period_day(label), float(v)))
    return sorted(out)


def parse_fred_csv(text: str, yoy: bool = False) -> list[tuple[str, float]]:
    rows = list(csv.reader(io.StringIO(text)))
    out = []
    for r in rows[1:]:
        if len(r) < 2:
            continue
        try:
            out.append((r[0][:10], float(r[1])))
        except ValueError:
            continue  # "." = fehlt
    out.sort()
    if yoy and out:
        s = pd.Series([v for _, v in out], index=pd.to_datetime([d for d, _ in out]))
        y = (s / s.shift(12) - 1) * 100
        out = [(d.strftime("%Y-%m-%d"), round(float(v), 2)) for d, v in y.dropna().items()]
    return out


def parse_worldbank(js) -> list[tuple[str, float]]:
    if not isinstance(js, list) or len(js) < 2 or not js[1]:
        return []
    out = []
    for row in js[1]:
        if row.get("value") is None:
            continue
        out.append((f"{row['date']}-12-31", round(float(row["value"]), 2)))
    return sorted(out)


def _period_day(label: str) -> str:
    """'2026-10' → '2026-10-28' (Monatsende), '2026-Q3' → Quartalsende, '2026-10-15' bleibt, '2025' → Jahresende."""
    s = str(label).strip()
    if len(s) == 10:
        return s
    if "Q" in s:
        y, q = s.split("-Q") if "-Q" in s else s.split("Q")
        month = int(q) * 3
        return (pd.Timestamp(int(y), month, 1) + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
    if len(s) == 7 or (len(s) == 8 and "M" in s):
        y, m = (s.split("-") if "-" in s else s.split("M"))
        return (pd.Timestamp(int(y), int(m), 1) + pd.offsets.MonthEnd(0)).strftime("%Y-%m-%d")
    if len(s) == 4:
        return f"{s}-12-31"
    return pd.Timestamp(s).strftime("%Y-%m-%d")


def fetch(series: Series) -> list[tuple[str, float]]:
    start = (date.today() - timedelta(days=365 * 12)).strftime("%Y-%m")
    if series.source == "ecb":
        flow, key = series.ref.split("|")
        return parse_ecb_csv(_get(ECB.format(flow=flow, key=key, start=start)).text)
    if series.source == "eurostat":
        ds, q = series.ref.split("|")
        return parse_eurostat(_get(EUROSTAT.format(ds=ds, q=q + "&sinceTimePeriod=" + start[:4])).json())
    if series.source == "fred":
        return parse_fred_csv(_get(FRED.format(id=series.ref)).text, yoy=series.yoy)
    if series.source == "worldbank":
        c, ind = series.ref.split("|")
        return parse_worldbank(_get(WORLDBANK.format(c=c, ind=ind)).json())
    raise ValueError(series.source)


def refresh(force: bool = False) -> int:
    """Alle Reihen holen, die älter als 6 Stunden sind. Gibt die Zahl erfolgreich geholter Reihen zurück."""
    store = marketstore.get_store()
    if store is None:
        return 0
    n = 0
    for s in SERIES:
        hit = store.get_with_age(f"macro:{s.id}")
        if hit and hit[1] < TTL and not force:
            continue
        try:
            data = fetch(s)
            if data:
                store.put(f"macro:{s.id}", {"points": data[-400:], "fetched": time.time()})
                n += 1
        except Exception as exc:  # noqa: BLE001
            log.info("Makroreihe %s nicht abrufbar: %s", s.id, exc)
    try:
        fg = fear_greed_fetch()
        if fg:
            store.put("mood:fear_greed", fg)
    except Exception as exc:  # noqa: BLE001
        log.info("Fear & Greed nicht abrufbar: %s", exc)
    return n


def points(series_id: str) -> list[tuple[str, float]]:
    store = marketstore.get_store()
    data = store.get(f"macro:{series_id}") if store else None
    return [tuple(p) for p in (data or {}).get("points", [])]


def _trend(pts: list[tuple[str, float]]) -> tuple[float | None, float | None]:
    if len(pts) < 2:
        return (pts[-1][1] if pts else None), None
    last = pts[-1][1]
    # Vergleich mit dem Wert vor ~3 Monaten (bzw. dem vorigen bei Quartals-/Jahreswerten)
    cutoff = (pd.Timestamp(pts[-1][0]) - pd.Timedelta(days=85)).strftime("%Y-%m-%d")
    older = [v for d, v in pts if d <= cutoff]
    prev = older[-1] if older else pts[-2][1]
    return last, round(last - prev, 3)


def indicators() -> list[dict]:
    """Für die Oberfläche: aktueller Wert, Veränderung, Einordnung."""
    out = []
    for s in SERIES:
        pts = points(s.id)
        if not pts:
            continue
        last, change = _trend(pts)
        tone = 0
        if change is not None and s.good and abs(change) > 1e-9:
            tone = 1 if (change > 0) == (s.good > 0) else -1
        out.append({"id": s.id, "label": s.label, "region": s.region, "unit": s.unit, "group": s.group,
                    "value": round(last, 2) if last is not None else None,
                    "change": round(change, 2) if change is not None else None, "as_of": pts[-1][0], "tone": tone,
                    "source": {"ecb": "EZB", "eurostat": "Eurostat", "fred": "FRED", "worldbank": "Weltbank"}[s.source],
                    "spark": [round(v, 3) for _, v in pts[-24:]]})
    return out


def regime() -> dict | None:
    """Grobe Einordnung des Umfelds aus Wachstum und Inflation (Euroraum, ersatzweise USA)."""
    growth = [_trend(points(i))[1] for i in ("ea_sentiment", "de_sentiment", "us_sentiment")]
    infl = [_trend(points(i))[1] for i in ("ea_inflation", "us_inflation")]
    g = [x for x in growth if x is not None]
    f = [x for x in infl if x is not None]
    if not g or not f:
        return None
    gu, iu = sum(g) / len(g) > 0, sum(f) / len(f) > 0
    names = {(True, False): ("Aufschwung, Inflation sinkt", "Günstig für Aktien: Stimmung steigt, Preisdruck lässt nach."),
             (True, True): ("Aufschwung mit Preisdruck", "Wachstum, aber steigende Inflation – Zinsen könnten hoch bleiben."),
             (False, True): ("Abschwung mit Preisdruck", "Schwierig: Stimmung fällt, Inflation steigt (Stagflationsrisiko)."),
             (False, False): ("Abkühlung, Inflation sinkt", "Wirtschaft kühlt ab, dafür sinkt der Preisdruck – Zinssenkungen "
                                                            "werden wahrscheinlicher.")}
    title, text = names[(gu, iu)]
    return {"growth_up": gu, "inflation_up": iu, "title": title, "text": text}


# ---------- Point-in-time-Werte fürs Modell ----------

def asof_frame(days: pd.DatetimeIndex, ids: list[str] | None = None) -> pd.DataFrame:
    """Je Tag der zu dem Zeitpunkt zuletzt *veröffentlichte* Wert jeder Reihe (Stichtag + Verzögerung)."""
    cols = {}
    for s in SERIES if ids is None else [BY_ID[i] for i in ids if i in BY_ID]:
        pts = points(s.id)
        if not pts:
            continue
        known = pd.Series([v for _, v in pts],
                          index=pd.to_datetime([d for d, _ in pts]) + pd.Timedelta(days=s.lag_days))
        known = known[~known.index.duplicated(keep="last")].sort_index()
        cols[s.id] = known.reindex(known.index.union(days)).ffill().reindex(days)
        # Veränderung über 3 Monate (Trend), ebenfalls nur aus Bekanntem
        cols[s.id + "_chg"] = cols[s.id] - cols[s.id].shift(63)
    return pd.DataFrame(cols, index=days)


# ---------- Marktstimmung (CNN Fear & Greed) ----------

def fear_greed_fetch() -> dict | None:
    r = requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
                     headers={**HEADERS, "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                                                        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
                              "Referer": "https://edition.cnn.com/"}, timeout=15)
    r.raise_for_status()
    js = r.json()
    fg = js.get("fear_and_greed") or {}
    hist = [(int(p["x"]) // 1000, float(p["y"])) for p in (js.get("fear_and_greed_historical") or {}).get("data", [])
            if p.get("y") is not None]
    if fg.get("score") is None:
        return None
    return {"score": round(float(fg["score"]), 1), "rating": fg.get("rating"), "previous_week": fg.get("previous_1_week"),
            "previous_month": fg.get("previous_1_month"), "history": hist[-400:], "fetched": time.time()}


RATINGS = {"extreme fear": "Extreme Angst", "fear": "Angst", "neutral": "Neutral", "greed": "Gier",
           "extreme greed": "Extreme Gier"}


def fear_greed() -> dict | None:
    store = marketstore.get_store()
    fg = store.get("mood:fear_greed") if store else None
    if not fg:
        return None
    return {**{k: v for k, v in fg.items() if k != "history"}, "label": RATINGS.get(fg.get("rating"), fg.get("rating")),
            "spark": [y for _, y in fg.get("history", [])[-60:]]}
