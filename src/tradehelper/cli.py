"""Kommandozeile: `tradehelper --help`."""

from __future__ import annotations

import json
import logging
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from . import __version__, alerts, analysis, market, news, notify
from .config import get_settings
from .report import build_report, send_report
from .storage import Storage

app = typer.Typer(help="TradeHelper – Kurse, Chartanalyse, Alarme und Morgenreport.", no_args_is_help=True)
wl_app = typer.Typer(help="Watchlist verwalten", no_args_is_help=True)
al_app = typer.Typer(help="Alarme verwalten", no_args_is_help=True)
app.add_typer(wl_app, name="watchlist")
app.add_typer(al_app, name="alert")
console = Console()


def _storage() -> Storage:
    return Storage(get_settings().db_path)


def _fail(msg: str) -> None:
    console.print(f"[red]{msg}[/red]")
    raise typer.Exit(1)


@app.command()
def version():
    """Version anzeigen."""
    console.print(__version__)


@app.command()
def serve(
    host: Optional[str] = typer.Option(None, help="Bind-Adresse"),
    port: Optional[int] = typer.Option(None, help="Port"),
    no_scheduler: bool = typer.Option(False, help="Ohne Morgenreport/Alarmprüfung starten"),
):
    """API-Server mit Scheduler starten (Dauerbetrieb, z. B. via systemd/Docker)."""
    import uvicorn

    from .scheduler import build_scheduler

    s = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sched = None
    if not no_scheduler:
        sched = build_scheduler(s)
        sched.start()
        for job in sched.get_jobs():
            logging.info("Job %s – nächster Lauf: %s", job.id, job.next_run_time)
    try:
        uvicorn.run("tradehelper.api:app", host=host or s.api_host, port=port or s.api_port, log_level="info")
    finally:
        if sched:
            sched.shutdown(wait=False)


@app.command()
def quote(symbols: list[str]):
    """Aktuelle Kurse abfragen, z. B. `tradehelper quote AAPL SAP.DE ^GDAXI`."""
    t = Table("Symbol", "Kurs", "Änderung", "%", "Währung")
    for sym in symbols:
        try:
            q = market.get_quote(sym)
        except market.MarketDataError as exc:
            t.add_row(sym.upper(), "[red]Fehler[/red]", str(exc), "", "")
            continue
        color = "green" if (q.change or 0) >= 0 else "red"
        t.add_row(q.symbol, f"{q.price:.2f}", f"[{color}]{q.change or 0:+.2f}[/{color}]",
                  f"[{color}]{q.change_pct or 0:+.2f}[/{color}]", q.currency or "")
    console.print(t)


@app.command()
def analyze(
    symbol: str,
    period: str = typer.Option("1y", help="Zeitraum (3mo, 6mo, 1y, 2y, 5y …)"),
    interval: str = typer.Option("1d", help="Kerzenintervall (1h, 1d, 1wk …)"),
    as_json: bool = typer.Option(False, "--json", help="Ausgabe als JSON"),
):
    """Chartanalyse mit Indikatoren, Signalen und Einschätzung."""
    s = get_settings()
    try:
        a = analysis.analyze(symbol, market.get_history(symbol, period, interval))
    except (market.MarketDataError, ValueError) as exc:
        _fail(str(exc))
    items = news.fetch_news(symbol, s.finnhub_api_key, s.news_lookback_days)
    rec = analysis.recommend(a, news.aggregate_sentiment(items))
    if as_json:
        console.print_json(json.dumps({**a.to_dict(), "recommendation": rec.__dict__}))
        return

    m = a.metrics
    console.print(f"\n[bold]{a.symbol}[/bold]  {a.last_close:.2f}  ({a.change_pct_1d or 0:+.2f} %)")
    t = Table("Kennzahl", "Wert", show_header=False)
    for label, k in [("SMA 20", "sma20"), ("SMA 50", "sma50"), ("SMA 200", "sma200"), ("RSI 14", "rsi"),
                     ("MACD / Signal", None), ("Bollinger %B", "bb_pctb"), ("Stoch %K/%D", None),
                     ("ADX", "adx"), ("ATR %", "atr_pct"), ("Perf. 1M / 3M %", None)]:
        if k:
            v = m.get(k)
            t.add_row(label, "–" if v is None else f"{v:.2f}")
    t.add_row("MACD / Signal", f"{m['macd'] or 0:.3f} / {m['signal'] or 0:.3f}")
    t.add_row("Stoch %K/%D", f"{m['stoch_k'] or 0:.1f} / {m['stoch_d'] or 0:.1f}")
    t.add_row("Perf. 1M / 3M %", f"{m['perf_1m'] or 0:+.1f} / {m['perf_3m'] or 0:+.1f}")
    t.add_row("Unterstützung / Widerstand", f"{a.support or '–'} / {a.resistance or '–'}")
    console.print(t)
    for sig in a.signals:
        c = "green" if sig.score > 0 else "red" if sig.score < 0 else "yellow"
        console.print(f"  [{c}]{sig.score:+d}[/{c}] {sig.name}: {sig.text}")
    if items:
        console.print(f"\n[bold]News[/bold] (Stimmung {news.aggregate_sentiment(items) or 0:+.2f})")
        for n in items[:5]:
            console.print(f"  • {n.headline}  [dim]{n.source}[/dim]")
    console.print(f"\n{rec.emoji} [bold]{rec.action}[/bold]  (Score {rec.combined:+.2f})")
    console.print("[dim]Regelbasierte Einschätzung – keine Anlageberatung.[/dim]")


@app.command()
def report(send: bool = typer.Option(False, "--send", help="Zusätzlich per ntfy versenden")):
    """Morgenreport für die Watchlist erzeugen."""
    st, s = _storage(), get_settings()
    if not st.watchlist_symbols():
        _fail("Watchlist ist leer. Erst `tradehelper watchlist add AAPL` ausführen.")
    rep = send_report(st, s) if send else build_report(st, s)
    console.print(Markdown(rep.to_markdown()))


@app.command("news")
def news_cmd(symbol: str, limit: int = 10):
    """Aktuelle Nachrichten mit Sentiment."""
    s = get_settings()
    if not s.finnhub_api_key:
        _fail("TH_FINNHUB_API_KEY ist nicht gesetzt.")
    items = news.fetch_news(symbol, s.finnhub_api_key, s.news_lookback_days, limit)
    for n in items:
        c = "green" if n.sentiment > 0 else "red" if n.sentiment < 0 else "white"
        console.print(f"[{c}]{n.sentiment:+.2f}[/{c}] {n.headline} [dim]({n.source})[/dim]")
    if not items:
        console.print("Keine Nachrichten gefunden.")


@app.command("notify-test")
def notify_test():
    """Testnachricht über ntfy senden."""
    ok = notify.send(get_settings(), "TradeHelper Test", "Benachrichtigungen funktionieren ✅")
    console.print("[green]Gesendet[/green]" if ok else "[red]Fehlgeschlagen – TH_NTFY_* prüfen[/red]")


# --- Watchlist ---------------------------------------------------------------
@wl_app.command("add")
def wl_add(symbols: list[str], note: str = ""):
    """Symbole hinzufügen."""
    st = _storage()
    for sym in symbols:
        st.add_symbol(sym, note)
    console.print(f"Hinzugefügt: {', '.join(s.upper() for s in symbols)}")


@wl_app.command("remove")
def wl_remove(symbols: list[str]):
    """Symbole entfernen."""
    st = _storage()
    for sym in symbols:
        console.print(f"{sym.upper()}: {'entfernt' if st.remove_symbol(sym) else 'nicht gefunden'}")


@wl_app.command("list")
def wl_list():
    """Watchlist anzeigen."""
    t = Table("Symbol", "Notiz", "Seit")
    for w in _storage().watchlist():
        t.add_row(w["symbol"], w["note"], w["added_at"][:10])
    console.print(t)


# --- Alarme ------------------------------------------------------------------
@al_app.command("kinds")
def al_kinds():
    """Verfügbare Alarmtypen und Parameter."""
    t = Table("Typ", "Beschreibung", "Parameter (Default)")
    for k in alerts.KINDS.values():
        t.add_row(k.name, k.description, ", ".join(f"{p}={'PFLICHT' if d is None else d}" for p, d in k.params.items()))
    console.print(t)


@al_app.command("add")
def al_add(
    symbol: str,
    kind: str,
    param: list[str] = typer.Option([], "--param", "-p", help="key=value, mehrfach möglich"),
    value: Optional[float] = typer.Option(None, "--value", "-v", help="Kurzform für -p value=…"),
    interval: str = typer.Option("1d", help="Kerzenintervall (5m, 15m, 1h, 1d …)"),
    once: bool = typer.Option(False, help="Nach dem ersten Auslösen deaktivieren"),
):
    """Alarm anlegen, z. B. `tradehelper alert add AAPL rsi_below -v 30`."""
    given = dict(p.split("=", 1) for p in param)
    if value is not None:
        given["value"] = value
    try:
        params = alerts.build_params(kind, given)
    except ValueError as exc:
        _fail(str(exc))
    aid = _storage().add_alert(symbol, kind, params, interval, once)
    console.print(f"Alarm #{aid} angelegt: {symbol.upper()} {kind} {params} [{interval}]")


@al_app.command("list")
def al_list():
    """Alarme anzeigen."""
    t = Table("ID", "Symbol", "Typ", "Parameter", "Intervall", "Aktiv", "Zuletzt")
    for a in _storage().alerts():
        t.add_row(str(a.id), a.symbol, a.kind, json.dumps(a.params), a.interval,
                  "ja" if a.active else "nein", (a.last_triggered or "–")[:16])
    console.print(t)


@al_app.command("remove")
def al_remove(alert_id: int):
    """Alarm löschen."""
    console.print("Gelöscht" if _storage().remove_alert(alert_id) else "Nicht gefunden")


@al_app.command("enable")
def al_enable(alert_id: int):
    """Alarm (wieder) aktivieren."""
    console.print("Aktiviert" if _storage().set_alert_active(alert_id, True) else "Nicht gefunden")


@al_app.command("disable")
def al_disable(alert_id: int):
    """Alarm pausieren."""
    console.print("Pausiert" if _storage().set_alert_active(alert_id, False) else "Nicht gefunden")


@al_app.command("check")
def al_check(dry_run: bool = typer.Option(False, help="Nicht senden, nur anzeigen")):
    """Alle aktiven Alarme jetzt prüfen."""
    fired = alerts.check_all(_storage(), get_settings(), send=not dry_run)
    for f in fired:
        console.print(f"🔔 #{f['id']} {f['symbol']}: {f['message']}")
    if not fired:
        console.print("Kein Alarm ausgelöst.")


@al_app.command("log")
def al_log(limit: int = 20):
    """Zuletzt ausgelöste Alarme."""
    for e in _storage().alert_log(limit):
        console.print(f"{e['triggered_at'][:16]}  #{e['alert_id']} {e['symbol']}: {e['message']}")


if __name__ == "__main__":
    app()
