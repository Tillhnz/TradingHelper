"""Hintergrund-Jobs: Morgenreport und periodische Alarmprüfung."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import alerts, report
from .config import Settings
from .storage import Storage

log = logging.getLogger(__name__)


def build_scheduler(settings: Settings) -> BackgroundScheduler:
    storage = Storage(settings.db_path)
    sched = BackgroundScheduler(timezone=settings.timezone)

    hh, mm = settings.report_time.split(":")
    sched.add_job(
        lambda: report.send_report(storage, settings),
        CronTrigger(day_of_week="mon-fri", hour=int(hh), minute=int(mm), timezone=settings.timezone),
        id="morning_report", max_instances=1, coalesce=True, misfire_grace_time=1800,
    )
    sched.add_job(
        lambda: _check(storage, settings),
        CronTrigger(day_of_week="mon-fri", hour=settings.alert_hours,
                    minute=f"*/{settings.alert_interval_minutes}", timezone=settings.timezone),
        id="alert_check", max_instances=1, coalesce=True,
    )
    return sched


def _check(storage: Storage, settings: Settings) -> None:
    fired = alerts.check_all(storage, settings)
    if fired:
        log.info("%d Alarm(e) ausgelöst", len(fired))
