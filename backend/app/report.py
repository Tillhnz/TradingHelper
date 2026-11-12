"""Morgenreport: Watchlist analysieren, News bewerten, Einschätzungen versenden."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

from . import analysis, entry, market, news, notify, portfolio
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
    holding: dict | None = None
    ticker: str | None = None


@dataclass
class Report:
    created: str
    entries: list[ReportEntry]
    errors: dict[str, str]
    profile: str = ""
    push_ok: bool = False
    status: str = ""  # Ergebnis des Versands für das Job-Protokoll

    def to_markdown(self) -> str:
        lines = [f"**TradeHelper Morgenreport – {self.created}**", f"Strategie: {self.profile}", ""]
        order = {"Kaufen prüfen": 0, "Reduzieren prüfen": 1, "Halten / beobachten": 2}
        for e in sorted(self.entries, key=lambda e: (order[e.rec.action], -abs(e.rec.combined))):
            a, r = e.analysis, e.rec
            chg = f"{a.change_pct_1d:+.2f} %" if a.change_pct_1d is not None else "–"
            ccy = f" {e.currency}" if e.currency else ""
            label = e.name or e.ticker or r.symbol
            lines.append(f"{r.emoji} **{label}** {a.last_close:.2f}{ccy} ({chg}) → **{r.action}** "
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
            h = e.holding
            if h and h.get("shares"):
                hc = f" {h['currency']}" if h.get("currency") else ""
                pl = f", {h['pl']:+.2f}{hc} ({h['pl_pct']:+.1f} %)" if h.get("pl") is not None else ""
                lines.append(f"  • 💼 Im Depot: {h['shares']:g} Stück{pl} → {h['advice']['text']}")
            elif e.plan and r.action != analysis.BUY:
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
                    "holding": e.holding,
                    "ticker": e.ticker,
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
    lots: dict[str, list] = {}
    for p in storage.positions():
        lots.setdefault(p["symbol"], []).append(p)
    entries: list[ReportEntry] = []
    errors: dict[str, str] = {}

    def one(w) -> tuple[str, ReportEntry | None, str | None]:
        sym = w["symbol"]
        try:
            df = market.get_history(sym, profile.period, "1d", currency=target)
            a = analysis.analyze(sym, df, profile)
            items = news.collect(sym, settings, w.get("name"))
            rec = analysis.recommend(a, news.aggregate_sentiment(items), news_count=sum(1 for i in items if i.sentiment))
            native = w.get("currency")
            if native is None and w.get("exchange") is None:
                native = market.guess_listing(sym)[1]
            shown = market.shown_currency(native, target)
            holding = None
            if lots.get(sym):
                holding = portfolio.summarize([portfolio.evaluate(p, profile) for p in lots[sym]], rec.action)
            return sym, ReportEntry(rec, a, items[:3], shown, w.get("name"), w.get("exchange"),
                                    entry.plan(a, rec, currency=shown), holding, w.get("ticker")), None
        except Exception as exc:  # noqa: BLE001
            log.warning("Report für %s fehlgeschlagen: %s", sym, exc)
            return sym, None, str(exc)

    # Mehrere Werte gleichzeitig (Nachrichten kommen von vielen Quellen); onvista drosselt gettex.py selbst
    with ThreadPoolExecutor(max_workers=6) as pool:
        for sym, e, err in pool.map(one, storage.watchlist()):
            if e:
                entries.append(e)
            else:
                errors[sym] = err
    created = datetime.now(ZoneInfo(settings.timezone)).strftime("%d.%m.%Y %H:%M")
    return Report(created, entries, errors, profile.label)


def short_text(rep: Report) -> str:
    """Kurzfassung für die Push-Benachrichtigung; der ganze Bericht steht auf der Webseite."""
    buy = [e for e in rep.entries if e.rec.action == analysis.BUY]
    sell = [e for e in rep.entries if e.rec.action == analysis.SELL]
    held_act = [e for e in rep.entries if e.holding and (e.holding.get("advice") or {}).get("level") in ("bad", "warn", "good")
                and e not in buy and e not in sell]
    name = lambda e: e.name or e.ticker or e.rec.symbol  # noqa: E731
    parts = [f"{len(rep.entries)} Werte geprüft: {len(buy)} Gelegenheit{'en' if len(buy) != 1 else ''}, "
             f"{len(sell)} × Vorsicht."]
    if buy:
        parts.append("🟢 " + ", ".join(name(e) for e in buy[:4]))
    if sell:
        parts.append("🔴 " + ", ".join(name(e) for e in sell[:4]))
    for e in held_act[:3]:
        parts.append(f"💼 {name(e)}: {e.holding['advice']['text']}")
    if rep.errors:
        parts.append(f"⚠️ {len(rep.errors)} Wert(e) ohne Daten")
    return "\n".join(parts)


KINDS = {"morning": "Morgenbericht", "afternoon": "Nachmittagsbericht"}


def send_report(storage: Storage, settings: Settings, kind: str = "morning") -> Report:
    """Bericht erstellen, speichern und als kurze Push-Nachricht melden. Antippen öffnet den Bericht auf der Webseite.
    Ohne bekannte Adresse der Oberfläche (app_url) kommt wie früher der ganze Bericht in die Nachricht."""
    rep = build_report(storage, settings)
    if not rep.entries and not rep.errors:
        rep.status = "übersprungen – keine Werte in der Watchlist"
        return rep
    title = KINDS.get(kind, "Bericht")
    rid = storage.save_report({**rep.to_dict(), "kind": kind, "title": title})
    tag = "sunrise" if kind == "morning" else "city_sunset"
    if notify.link(settings):
        ok = notify.send(settings, f"Dein {title} ist da", short_text(rep) + "\nAntippen für den ganzen Bericht.",
                         tags=[tag], path=f"/?bericht={rid}")
    else:
        ok = notify.send(settings, f"TradeHelper {title}", rep.to_markdown(), tags=[tag])
    rep.push_ok = ok or not settings.ntfy_topic
    done = f"{len(rep.entries)} Werte" + (f", {len(rep.errors)} ohne Daten" if rep.errors else "")
    if ok:
        rep.status = f"{done} · Push gesendet"
    elif not settings.ntfy_topic:
        rep.status = f"{done} · Bericht gespeichert, kein Push (kein ntfy-Topic hinterlegt)"
    else:
        rep.status = f"{done} · Bericht gespeichert, Push fehlgeschlagen: {notify.last_error}"
    return rep
