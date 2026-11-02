"""Hintergrund-Jobs: Morgenreport und Alarmprüfung. Wird neu geplant, wenn sich Einstellungen ändern."""

from __future__ import annotations

import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import alerts, report
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


def _plan(sched: BackgroundScheduler, storage: Storage, settings: Settings) -> None:
    for job in sched.get_jobs():
        job.remove()
    tz = settings.timezone
    if settings.report_enabled:
        hh, mm = settings.report_time.split(":")
        sched.add_job(
            lambda: report.send_report(storage, settings),
            CronTrigger(day_of_week=_days(settings.report_weekends), hour=int(hh), minute=int(mm), timezone=tz),
            id="morning_report", max_instances=1, coalesce=True, misfire_grace_time=1800,
        )
    if settings.alerts_enabled:
        sched.add_job(
            lambda: _check(storage, settings),
            CronTrigger(day_of_week=_days(settings.alert_weekends),
                        hour=_hours(settings.alert_start_hour, settings.alert_end_hour),
                        minute=f"*/{settings.alert_interval_minutes}", timezone=tz),
            id="alert_check", max_instances=1, coalesce=True,
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
