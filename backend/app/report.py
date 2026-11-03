"""Morgenreport: Watchlist analysieren, News bewerten, Einschätzungen versenden."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from . import analysis, market, news, notify
from .config import Settings
from .storage import Storage

log = logging.getLogger(__name__)

DISCLAIMER = "_Automatisch erzeugte, regelbasierte Einschätzung – keine Anlageberatung._"


@dataclass
class ReportEntry:
    rec: analysis.Recommendation
    analysis: analysis.Analysis
    headlines: list[news.NewsItem] = field(default_factory=list)
    currency: str | None = None
    name: str | None = None
    exchange: str | None = None


@dataclass
class Report:
    created: str
    entries: list[ReportEntry]
    errors: dict[str, str]

    def to_markdown(self) -> str:
        lines = [f"**TradeHelper Morgenreport – {self.created}**", ""]
        order = {"Kaufen prüfen": 0, "Reduzieren prüfen": 1, "Halten / beobachten": 2}
        for e in sorted(self.entries, key=lambda e: (order[e.rec.action], -abs(e.rec.combined))):
            a, r = e.analysis, e.rec
            chg = f"{a.change_pct_1d:+.2f} %" if a.change_pct_1d is not None else "–"
            ccy = f" {e.currency}" if e.currency else ""
            lines.append(f"{r.emoji} **{r.symbol}** {a.last_close:.2f}{ccy} ({chg}) → **{r.action}** "
                         f"(Score {r.combined:+.2f})")
            for reason in r.reasons:
                lines.append(f"  • {reason}")
            if a.support or a.resistance:
                sup = f"{a.support:.2f}" if a.support else "–"
                res = f"{a.resistance:.2f}" if a.resistance else "–"
                lines.append(f"  • Unterstützung {sup} / Widerstand {res}")
            if e.headlines:
                lines.append(f"  • News: {e.headlines[0].headline[:110]}")
            lines.append("")
        for sym, err in self.errors.items():
            lines.append(f"⚠️ {sym}: {err}")
        lines += ["", DISCLAIMER]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "created": self.created,
            "entries": [
                {
                    "symbol": e.rec.symbol,
                    "action": e.rec.action,
                    "combined_score": e.rec.combined,
                    "technical_score": e.rec.technical,
                    "sentiment": e.rec.sentiment,
                    "reasons": e.rec.reasons,
                    "analysis": e.analysis.to_dict(),
                    "news": [n.to_dict() for n in e.headlines],
                    "currency": e.currency,
                    "name": e.name,
                    "exchange": e.exchange,
                }
                for e in self.entries
            ],
            "errors": self.errors,
            "disclaimer": DISCLAIMER,
        }


def target_currency(settings: Settings) -> str | None:
    c = settings.display_currency
    return None if not c or c == "native" else c


def build_report(storage: Storage, settings: Settings) -> Report:
    target = target_currency(settings)
    entries: list[ReportEntry] = []
    errors: dict[str, str] = {}
    for w in storage.watchlist():
        sym = w["symbol"]
        try:
            df = market.get_history(sym, settings.history_period, "1d", currency=target)
            a = analysis.analyze(sym, df)
            items = news.fetch_news(sym, settings.finnhub_api_key, settings.news_lookback_days)
            rec = analysis.recommend(a, news.aggregate_sentiment(items), settings.news_weight / 100)
            native = w.get("currency")
            if native is None and w.get("exchange") is None:
                native = market.guess_listing(sym)[1]
            entries.append(ReportEntry(rec, a, items[:3], market.shown_currency(native, target),
                                       w.get("name"), w.get("exchange")))
        except Exception as exc:  # noqa: BLE001
            log.warning("Report für %s fehlgeschlagen: %s", sym, exc)
            errors[sym] = str(exc)
    created = datetime.now(ZoneInfo(settings.timezone)).strftime("%d.%m.%Y %H:%M")
    return Report(created, entries, errors)


def send_report(storage: Storage, settings: Settings) -> Report:
    rep = build_report(storage, settings)
    if not rep.entries and not rep.errors:
        notify.send(settings, "TradeHelper Morgenreport", "Watchlist ist leer – nichts zu berichten.")
        return rep
    notify.send(settings, "TradeHelper Morgenreport", rep.to_markdown(), tags=["sunrise"])
    return rep
