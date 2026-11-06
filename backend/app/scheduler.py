"""Hintergrund-Jobs: Morgenreport und Alarmprüfung. Wird neu geplant, wenn sich Einstellungen ändern."""

from __future__ import annotations

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import alerts, paper, portfolio, report, settings_store
from .config import Settings
from .storage import Storage

log = logging.getLogger(__name__)

_sched: BackgroundScheduler | None = None
_lock = threading.Lock()


def _days(weekends: bool) -> str:
    return "mon-sun" if weekends else "mon-fri"


def _hours(start: int, end: int) -> str:
    if start == end:
        return str(start)
    if start < end:
        return f"{start}-{end}"
    return f"{start}-23,0-{end}"  # über Mitternacht, z. B. 15-2 für US-Handel plus Nachbörse


def _each_user(storage: Storage, base: Settings, job, label: str) -> None:
    """Führt einen Job für jeden Nutzer mit seinen Daten und Einstellungen aus. Fehler eines Nutzers stoppen die
    anderen nicht."""
    for u in storage.users():
        st = storage.for_user(u["id"])
        try:
            job(st, settings_store.for_user(st, base))
        except Exception:  # noqa: BLE001
            log.exception("%s für Nutzer %s fehlgeschlagen", label, u["username"])


def _plan(sched: BackgroundScheduler, storage: Storage, settings: Settings) -> None:
    for job in sched.get_jobs():
        job.remove()
    tz = settings.timezone
    # Morgen- und Nachmittagsbericht; direkt danach handelt das Schattendepot (oder platziert Orders)
    if settings.report_enabled:
        for kind, at in (("morning", settings.report_time), ("afternoon", settings.report_time_pm)):
            if not at:
                continue
            hh, mm = at.split(":")
            sched.add_job(
                lambda kind=kind: _each_user(storage, settings, lambda st, cfg: _report_and_trade(st, cfg, kind),
                                             "Bericht"),
                CronTrigger(day_of_week=_days(settings.report_weekends), hour=int(hh), minute=int(mm), timezone=tz),
                id=f"{kind}_report", max_instances=1, coalesce=True, misfire_grace_time=1800,
            )
    if settings.alerts_enabled:
        sched.add_job(
            lambda: _each_user(storage, settings, _check, "Alarmprüfung"),
            CronTrigger(day_of_week=_days(settings.alert_weekends),
                        hour=_hours(settings.alert_start_hour, settings.alert_end_hour),
                        minute=f"*/{settings.alert_interval_minutes}", timezone=tz),
            id="alert_check", max_instances=1, coalesce=True,
        )
    # Platzierte Orders des Schattendepots während der Handelszeit prüfen (unabhängig von den Alarmen)
    sched.add_job(
        lambda: _each_user(storage, settings, _paper_orders, "Schattendepot-Orders"),
        CronTrigger(day_of_week="mon-fri", hour="8-21", minute="*/10", timezone=tz),
        id="paper_orders", max_instances=1, coalesce=True,
    )
    # Einmal pro Woche den Rückblick neu rechnen, damit neue Kurse und Werte einfließen
    sched.add_job(
        lambda: _each_user(storage, settings, lambda st, cfg: cfg.paper_enabled and paper.run_backtest(st, cfg),
                           "Rückblick"),
        CronTrigger(day_of_week="sun", hour=4, minute=17, timezone=tz),
        id="paper_backtest", max_instances=1, coalesce=True, misfire_grace_time=6 * 3600,
    )


def start(storage: Storage, settings: Settings) -> None:
    global _sched
    with _lock:
        if _sched is not None:
            return
        _sched = BackgroundScheduler(timezone=settings.timezone)
        _plan(_sched, storage, settings)
        _sched.start()
        log.info("Scheduler gestartet: %s", next_runs())


def replan(storage: Storage, settings: Settings) -> None:
    with _lock:
        if _sched is not None:
            _plan(_sched, storage, settings)
            log.info("Zeitplan aktualisiert: %s", next_runs())


def stop() -> None:
    global _sched
    with _lock:
        if _sched is not None:
            _sched.shutdown(wait=False)
            _sched = None


def next_runs() -> dict[str, str | None]:
    if _sched is None:
        return {}
    return {j.id: j.next_run_time.isoformat() if j.next_run_time else None for j in _sched.get_jobs()}


def _check(storage: Storage, settings: Settings) -> None:
    try:
        fired = alerts.check_all(storage, settings)
        if fired:
            log.info("%d Alarm(e) ausgelöst", len(fired))
    except Exception:  # noqa: BLE001
        log.exception("Alarmprüfung fehlgeschlagen")
    try:
        sent = portfolio.watch(storage, settings)
        if sent:
            log.info("%d Depot-Hinweis(e) verschickt", len(sent))
    except Exception:  # noqa: BLE001
        log.exception("Depot-Prüfung fehlgeschlagen")


def _report_and_trade(storage: Storage, settings: Settings, kind: str) -> None:
    try:
        report.send_report(storage, settings, kind)
    finally:
        _paper(storage, settings)


def _paper_orders(storage: Storage, settings: Settings) -> None:
    if settings.paper_enabled:
        paper.check_orders(storage, settings)


def _paper(storage: Storage, settings: Settings) -> None:
    if not settings.paper_enabled or not storage.watchlist():
        return
    try:
        res = paper.run_live(storage, settings)
        log.info("Schattendepot: %d Order(s), Wert %.2f", len(res["trades"]), res["equity"])
    except Exception:  # noqa: BLE001
        log.exception("Schattendepot-Lauf fehlgeschlagen")
