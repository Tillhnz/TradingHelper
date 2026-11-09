from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("apscheduler")

from app import report, scheduler  # noqa: E402
from app.config import Settings  # noqa: E402
from app.storage import Storage  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")


def cfg(**kw):
    s = Settings()
    s.report_time, s.report_time_pm, s.report_weekends, s.report_enabled = "07:00", "16:00", False, True
    s.timezone = "Europe/Berlin"
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_last_due_picks_latest_passed_slot():
    s = cfg()
    assert scheduler._last_due(s, datetime(2026, 11, 9, 6, 59, tzinfo=TZ)) is None  # Montag, noch nichts fällig
    kind, t = scheduler._last_due(s, datetime(2026, 11, 9, 12, 56, tzinfo=TZ))
    assert kind == "morning" and t.hour == 7
    assert scheduler._last_due(s, datetime(2026, 11, 9, 17, 0, tzinfo=TZ))[0] == "afternoon"
    assert scheduler._last_due(s, datetime(2026, 11, 8, 12, 0, tzinfo=TZ)) is None  # Sonntag ohne Wochenend-Bericht
    assert scheduler._last_due(cfg(report_time_pm=""), datetime(2026, 11, 9, 17, 0, tzinfo=TZ))[0] == "morning"


def test_job_log_and_ran_since(tmp_path):
    st = Storage(tmp_path / "t.db")
    jid = st.job_start("morning_report")
    assert st.job_runs()[0]["status"] == "running"
    st.job_finish(jid, "warn", "5 Werte · Push fehlgeschlagen: 403")
    run = st.job_runs()[0]
    assert run["status"] == "warn" and "403" in run["detail"] and run["finished_at"]
    assert st.ran_since("morning_report", "2000-01-01T00:00:00+00:00")
    assert not st.ran_since("afternoon_report", "2000-01-01T00:00:00+00:00")
    assert not st.ran_since("morning_report", "2999-01-01T00:00:00+00:00")


def test_catch_up_runs_missing_report_once(tmp_path, monkeypatch):
    st = Storage(tmp_path / "t.db")
    calls = []
    monkeypatch.setattr(scheduler, "_each_user", lambda storage, settings, job, label: job(storage, settings))
    monkeypatch.setattr(scheduler, "_report_and_trade", lambda s, c, kind: (calls.append(kind), s.job_start(f"{kind}_report")))

    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 9, 12, 56, tzinfo=TZ)

    monkeypatch.setattr(scheduler, "datetime", Fixed)
    scheduler.catch_up(st, cfg())
    scheduler.catch_up(st, cfg())
    assert calls == ["morning"]


def test_send_report_status_without_topic(tmp_path, monkeypatch):
    st = Storage(tmp_path / "t.db")
    rep = report.Report("09.11.2026 07:00", [object()], {}, "x")
    monkeypatch.setattr(report, "build_report", lambda s, c: rep)
    monkeypatch.setattr(report.Report, "to_dict", lambda self: {})
    monkeypatch.setattr(report, "short_text", lambda r: "kurz")
    monkeypatch.setattr(report.Report, "to_markdown", lambda self: "lang")
    out = report.send_report(st, cfg(ntfy_topic=""), "morning")
    assert "kein ntfy-Topic" in out.status  # ohne Topic ist das kein Fehler, nur ohne Push


def test_short_text_with_fully_sold_holding():
    """Alles verkauft: summarize() liefert advice=None – der Bericht darf daran nicht scheitern."""
    from types import SimpleNamespace

    from app import analysis
    sold = {"shares": 0, "advice": None, "currency": "EUR", "lots": 0, "closed_lots": 1}
    held = {"shares": 5, "advice": {"level": "warn", "text": "Stopp nachziehen"}}
    e1 = SimpleNamespace(rec=SimpleNamespace(action=analysis.HOLD, symbol="A"), holding=sold, name="Alpha", ticker=None)
    e2 = SimpleNamespace(rec=SimpleNamespace(action=analysis.HOLD, symbol="B"), holding=held, name="Beta", ticker=None)
    txt = report.short_text(report.Report("x", [e1, e2], {}, "p"))
    assert "Beta: Stopp nachziehen" in txt and "Alpha:" not in txt
