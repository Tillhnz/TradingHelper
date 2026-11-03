"""Morgenreport: Watchlist analysieren, News bewerten, Einschätzungen versenden."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from . import analysis, entry, market, news, notify
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
    plan: dict | None = None


@dataclass
class Report:
    created: str
    entries: list[ReportEntry]
    errors: dict[str, str]
    profile: str = ""

    def to_markdown(self) -> str:
        lines = [f"**TradeHelper Morgenreport – {self.created}**", f"Strategie: {self.profile}", ""]
        order = {"Kaufen prüfen": 0, "Reduzieren prüfen": 1, "Halten / beobachten": 2}
        for e in sorted(self.entries, key=lambda e: (order[e.rec.action], -abs(e.rec.combined))):
            a, r = e.analysis, e.rec
            chg = f"{a.change_pct_1d:+.2f} %" if a.change_pct_1d is not None else "–"
            ccy = f" {e.currency}" if e.currency else ""
            lines.append(f"{r.emoji} **{r.symbol}** {a.last_close:.2f}{ccy} ({chg}) → **{r.action}** "
                         f"(Score {r.combined:+.2f})")
            for reason in r.reasons:
                lines.append(f"  • {reason}")
            levels = []
            if r.stop:
                levels.append(f"Stopp {r.stop:.2f}")
            if r.target:
                levels.append(f"Ziel {r.target:.2f}")
            if r.crv:
                levels.append(f"CRV {r.crv:.1f}")
            if levels:
                lines.append("  • " + " · ".join(levels))
            if r.position:
                lines.append(f"  • Positionsgröße: {r.position['shares']} Stück ≈ {r.position['value']:.0f}{ccy}, "
                             f"Risiko {r.position['risk']:.0f}{ccy} ({r.position['risk_pct']} % des Depots)")
            if e.plan and r.action != analysis.BUY:
                lines.append(f"  • {e.plan['summary']}")
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
                    "stop": e.rec.stop,
                    "target": e.rec.target,
                    "crv": e.rec.crv,
                    "position": e.rec.position,
                    "analysis": e.analysis.to_dict(),
                    "news": [n.to_dict() for n in e.headlines],
                    "currency": e.currency,
                    "name": e.name,
                    "exchange": e.exchange,
                    "entry": e.plan,
                }
                for e in self.entries
            ],
            "errors": self.errors,
            "profile": self.profile,
            "disclaimer": DISCLAIMER,
        }


def target_currency(settings: Settings) -> str | None:
    c = settings.display_currency
    return None if not c or c == "native" else c


def build_report(storage: Storage, settings: Settings) -> Report:
    target = target_currency(settings)
    profile = analysis.profile_from(settings)
    entries: list[ReportEntry] = []
    errors: dict[str, str] = {}
    for w in storage.watchlist():
        sym = w["symbol"]
        try:
            df = market.get_history(sym, profile.period, "1d", currency=target)
            a = analysis.analyze(sym, df, profile)
            items = news.fetch_news(sym, settings.finnhub_api_key, settings.news_lookback_days)
            rec = analysis.recommend(a, news.aggregate_sentiment(items))
            native = w.get("currency")
            if native is None and w.get("exchange") is None:
                native = market.guess_listing(sym)[1]
            shown = market.shown_currency(native, target)
            entries.append(ReportEntry(rec, a, items[:3], shown, w.get("name"), w.get("exchange"),
                                       entry.plan(a, rec, currency=shown)))
        except Exception as exc:  # noqa: BLE001
            log.warning("Report für %s fehlgeschlagen: %s", sym, exc)
            errors[sym] = str(exc)
    created = datetime.now(ZoneInfo(settings.timezone)).strftime("%d.%m.%Y %H:%M")
    return Report(created, entries, errors, profile.label)


def send_report(storage: Storage, settings: Settings) -> Report:
    rep = build_report(storage, settings)
    if not rep.entries and not rep.errors:
        notify.send(settings, "TradeHelper Morgenreport", "Watchlist ist leer – nichts zu berichten.")
        return rep
    notify.send(settings, "TradeHelper Morgenreport", rep.to_markdown(), tags=["sunrise"])
    return rep
