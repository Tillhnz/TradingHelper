"""Marktumfeld, Konjunktur, Stimmung und Modell – alles aus vorberechneten Speichern, damit es sofort da ist."""

from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException

from . import analysis, brain, drivers, macro, market, marketstore, social
from .config import Settings
from .config import settings as base_settings
from .deps import auth, get_storage, require_admin, user_cfg, user_storage
from .storage import Storage

router = APIRouter(dependencies=auth)
log = logging.getLogger(__name__)
_SOCIAL_BUSY: set[str] = set()
_SOCIAL_LOCK = threading.Lock()


def _spark(symbol: str, n: int = 30) -> list[float]:
    store = marketstore.get_store()
    if store is None:
        return []
    df = store.daily(symbol)
    return [round(float(x), 4) for x in df["close"].tail(n)] if not df.empty else []


@router.get("/api/markets")
def markets():
    """Indizes, Rohstoffe, Devisen für die Startseite (Kurse aus dem Speicher des Hintergrunddienstes)."""
    store = marketstore.get_store()
    quotes = store.quotes(macro.MARKET_SYMBOLS) if store else {}
    out = []
    for sym, label in macro.MARKETS:
        q = (quotes.get(sym) or ({}, 0))[0]
        price, prev = q.get("price"), q.get("previous_close")
        spark = _spark(sym)
        if price is None and spark:
            price = spark[-1]
            prev = spark[-2] if len(spark) > 1 else None
        out.append({"symbol": sym, "label": label, "price": price, "previous_close": prev,
                    "change_pct": round((price / prev - 1) * 100, 2) if price and prev else None,
                    "currency": q.get("native"), "spark": spark, "time": q.get("time")})
    return {"items": out}


@router.get("/api/macro")
def macro_view():
    return {"indicators": macro.indicators(), "regime": macro.regime(), "fear_greed": macro.fear_greed(),
            "sources": ["EZB", "Eurostat", "FRED", "Weltbank", "CNN Fear & Greed"]}


def _refresh_social(symbol: str, st: Storage) -> None:
    with _SOCIAL_LOCK:
        if symbol in _SOCIAL_BUSY:
            return
        _SOCIAL_BUSY.add(symbol)

    def run():
        try:
            social.refresh(st, [symbol], force=True)
        except Exception as exc:  # noqa: BLE001
            log.info("Social %s: %s", symbol, exc)
        finally:
            with _SOCIAL_LOCK:
                _SOCIAL_BUSY.discard(symbol)

    threading.Thread(target=run, daemon=True).start()


@router.get("/api/social/{symbol}")
def social_view(symbol: str, st: Storage = Depends(user_storage)):
    sym = symbol.upper()
    data = social.get(sym)
    stale = not data or time.time() - (data.get("fetched") or 0) > social.TTL
    if stale and base_settings.social_enabled:
        _refresh_social(sym, st)
    return {"symbol": sym, "data": data, "refreshing": bool(stale and base_settings.social_enabled),
            "history": social.history(sym), "enabled": base_settings.social_enabled}


@router.get("/api/why/{symbol}")
def why(symbol: str, budget: float = 3.0, refresh: bool = False, settings: Settings = Depends(user_cfg)):
    """Warum läuft der Wert so? Markt/Branche/Eigenes, stärkste Tage mit Schlagzeilen, Nachrichtenlage."""
    return drivers.get(symbol, settings, budget=max(0.2, min(budget, 8)), force=refresh)


@router.get("/api/mood")
def mood(st: Storage = Depends(user_storage)):
    """Marktstimmung: Fear & Greed plus Social-Stimmung über die eigenen Werte."""
    items = []
    for w in st.watchlist():
        d = social.get(w["symbol"])
        if d and (d.get("n") or d.get("attention")):
            items.append({"symbol": w["symbol"], "name": w.get("name") or d.get("name"), "score": d.get("score"),
                          "n": d.get("n"), "buzz": d.get("buzz"), "bull_ratio": d.get("bull_ratio"),
                          "attention": (d.get("attention") or {}).get("ratio")})
    scored = [i for i in items if i["score"] is not None and i["n"]]
    avg = round(sum(i["score"] * i["n"] for i in scored) / sum(i["n"] for i in scored), 3) if scored else None
    loud = sorted([i for i in items if (i.get("buzz") or 0) > 1.5 or (i.get("attention") or 0) > 1.8],
                  key=lambda i: -max(i.get("buzz") or 0, i.get("attention") or 0))[:5]
    return {"fear_greed": macro.fear_greed(), "social": avg, "items": sorted(items, key=lambda i: -(i["n"] or 0)),
            "loud": loud}


# ---------- Modell ----------

def model_view(symbol: str, rec: analysis.Recommendation, profile: analysis.Profile) -> dict | None:
    """Modell-Einschätzung für die Seite eines Werts: Wahrscheinlichkeiten, Treiber, Kombination mit den Regeln."""
    try:
        store = marketstore.get_store()
        key = f"pred:{profile.horizon}:{symbol.upper()}"
        pred = store.get(key, max_age=20 * 3600) if store else None
        if pred is None:
            pred = brain.predict(symbol, profile.horizon)
            if pred and store:
                store.put(key, pred)
        if not pred:
            return None
        w = brain.weight(profile.horizon)
        comb = brain.combine(rec.combined, rec.action, pred, w, profile)
        _, meta = brain.load(profile.horizon)
        return {**{k: v for k, v in pred.items() if k != "features"}, "weight": w, "final": comb,
                "rule": {"action": rec.action, "score": rec.combined},
                "model_summary": (meta or {}).get("summary"), "trained_to": (meta or {}).get("to")}
    except Exception as exc:  # noqa: BLE001
        log.info("Modell für %s nicht verfügbar: %s", symbol, exc)
        return None


@router.get("/api/model")
def model_overview(st: Storage = Depends(get_storage)):
    return brain.overview(st)


@router.get("/api/model/decisions")
def model_decisions(symbol: str | None = None, limit: int = 100, st: Storage = Depends(user_storage)):
    """Entscheidungsjournal für die eigenen Werte (oder einen Wert)."""
    if symbol:
        syms = [symbol.upper()]
    else:
        syms = [w["symbol"] for w in st.watchlist()]
        syms += [p["symbol"] for p in st.positions(open_only=True) if p["symbol"] not in syms]
    rows = st.decisions(symbols=syms, limit=max(1, min(limit, 500)))
    for r in rows:
        r.pop("features", None)
        r["name"] = (market.cached_info(r["symbol"]) or {}).get("name")
    return {"items": rows}


@router.post("/api/model/train", dependencies=[Depends(require_admin)], status_code=202)
def model_train(st: Storage = Depends(get_storage)):
    if not brain.start_training(st, base_settings):
        raise HTTPException(409, "Das Modell lernt gerade schon.")
    return {"started": True}


@router.get("/api/model/status")
def model_status():
    return brain.STATUS


@router.get("/api/model/symbol/{symbol}")
def model_symbol(symbol: str, settings: Settings = Depends(user_cfg)):
    from . import snapshot

    profile = analysis.profile_from(settings)
    try:
        _, _, rec = snapshot.technical(symbol, profile, None)
    except market.MarketDataError as exc:
        raise HTTPException(404, str(exc)) from exc
    return model_view(symbol, rec, profile) or {"available": False}
