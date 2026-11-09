"""Update-Wächter: neue Versionen einmal an Administratoren pushen."""

def test_update_watch_pushes_each_version_once(tmp_path):
    from app import updatewatch
    from app.config import Settings
    from app.storage import Storage
    st = Storage(tmp_path / "u.db")
    st.create_user("chef", "x")
    st.create_user("gast", "x")
    sent = []
    status = lambda: {"behind": 2, "changes": ["2026-11-09  Bump requests from 2.33.0 to 2.33.1 in /backend (#9)", "2026-11-08  x"]}  # noqa: E731
    send = lambda cfg, title, body, **kw: sent.append((title, kw["priority"])) or True  # noqa: E731
    base = Settings()
    base.update_notify = True
    assert updatewatch.run(st, base, status, send) == 1  # nur der Administrator
    assert updatewatch.run(st, base, status, send) == 0  # gleiche Version nicht nochmal
    assert sent == [("Sicherheitsupdate für TradeHelper verfügbar", "high")]
