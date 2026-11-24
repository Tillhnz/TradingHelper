import time

from app import analysis, news, snapshot, verdict


def test_overview_row_uses_same_verdict_as_detail(uptrend, monkeypatch):
    """Liste und Seite eines Werts müssen gleich urteilen – auch wenn News die Technik kippen."""
    monkeypatch.setattr(snapshot.market, "get_history", lambda *a, **k: uptrend)
    profile = analysis.Profile("medium")
    a = analysis.analyze("TEST.DE", uptrend, profile)
    tech_only = analysis.recommend(snapshot._copy(a), None, profile)
    # stark negative Nachrichten, wie sie der Abruf auf der Seite des Werts misst
    with news._SENT_LOCK:
        news._SENT["TEST.DE"] = (time.time(), -1.0, 8)
    detail = verdict.final(snapshot._copy(a), profile, -1.0, 8)
    row = snapshot.compute_row({"symbol": "TEST.DE", "currency": "EUR"}, profile, None)
    assert row["action"] == detail.action
    assert row["score"] == detail.combined
    assert detail.combined < tech_only.combined


def test_cached_sentiment_expires():
    with news._SENT_LOCK:
        news._SENT["OLD.DE"] = (time.time() - 10 * 3600, 0.5, 3)
    assert news.cached_sentiment("OLD.DE") is None
    assert news.cached_sentiment("NOPE.DE") is None
