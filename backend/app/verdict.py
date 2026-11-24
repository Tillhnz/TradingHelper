"""Die eine Einschätzung je Wert – überall gleich: Übersicht, Seite des Werts, Startseite, Berichte.

Regeln (Technik) + News-Stimmung + lernendes Modell (wenn es genug kann). Vorher rechnete die Übersicht nur mit
der Technik, die Seite des Werts zusätzlich mit News – dadurch stand in der Liste „Kaufen?“ und auf der Seite
„Abwarten“. Jetzt laufen alle Stellen durch final()."""

from __future__ import annotations

import dataclasses
import logging

from . import analysis, marketstore, news

log = logging.getLogger(__name__)


def _prediction(symbol: str, horizon: str) -> dict | None:
    store = marketstore.get_store()
    if store is None:
        return None
    try:
        return store.get(f"pred:{horizon}:{symbol.upper()}", max_age=4 * 86400)
    except Exception:  # noqa: BLE001
        return None


def final(a: analysis.Analysis, profile: analysis.Profile, sentiment: float | None = None, news_count: int = 0,
          use_cached_news: bool = False, settings=None, pred: dict | None = None) -> analysis.Recommendation:
    """Einschätzung aus Regeln, News und Modell. Mit use_cached_news wird die zuletzt gemessene News-Stimmung des
    Werts genommen (ohne Netz). Das Ergebnis trägt in notes den Hinweis, wenn das Modell die Regeln überstimmt hat."""
    if use_cached_news and sentiment is None:
        hit = news.cached_sentiment(a.symbol)
        if hit:
            sentiment, news_count = hit
    rec = analysis.recommend(a, sentiment, profile, news_count=news_count)
    try:
        from . import brain

        w = brain.weight(profile.horizon, settings)
        pred = pred if pred is not None else _prediction(a.symbol, profile.horizon)
        if pred and w > 0:
            comb = brain.combine(rec.combined, rec.action, pred, w, profile)
            if comb["action"] != rec.action:
                ui = {analysis.BUY: "Kaufen", analysis.HOLD: "Abwarten", analysis.SELL: "Reduzieren"}
                rec.notes = [*rec.notes, f"Das lernende Modell ändert die Regel-Einschätzung „{ui.get(rec.action, rec.action)}“ "
                                         f"zu „{ui.get(comb['action'], comb['action'])}“."]
            rec = dataclasses.replace(rec, action=comb["action"], combined=comb["score"])
    except Exception as exc:  # noqa: BLE001
        log.debug("Modell nicht einbezogen für %s: %s", a.symbol, exc)
    return rec
