import sqlite3

from app.storage import Storage

OLD = """
CREATE TABLE watchlist (symbol TEXT PRIMARY KEY, note TEXT DEFAULT '', added_at TEXT NOT NULL, name TEXT, exchange TEXT,
    currency TEXT, ticker TEXT);
CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, kind TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}', interval TEXT NOT NULL DEFAULT '1d', once INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1, last_triggered TEXT, created_at TEXT NOT NULL, currency TEXT NOT NULL DEFAULT '');
CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
    token_version INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE positions (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT NOT NULL, quantity REAL NOT NULL,
    buy_price REAL NOT NULL, buy_date TEXT NOT NULL, fees REAL NOT NULL DEFAULT 0, currency TEXT NOT NULL DEFAULT '',
    stop REAL, target REAL, note TEXT NOT NULL DEFAULT '', sell_price REAL, sell_date TEXT,
    sell_fees REAL NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE paper_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE paper_equity (day TEXT PRIMARY KEY, equity REAL NOT NULL, cash REAL NOT NULL);
CREATE TABLE alert_log (id INTEGER PRIMARY KEY AUTOINCREMENT, alert_id INTEGER NOT NULL, symbol TEXT NOT NULL,
    message TEXT NOT NULL, triggered_at TEXT NOT NULL);
INSERT INTO users(username, password_hash, created_at) VALUES ('till', 'h', 'x');
INSERT INTO watchlist(symbol, added_at, name) VALUES ('SAP.DE', 'x', 'SAP');
INSERT INTO alerts(symbol, kind, created_at) VALUES ('SAP.DE', 'price_above', 'x');
INSERT INTO positions(symbol, quantity, buy_price, buy_date, created_at) VALUES ('SAP.DE', 5, 100, '2026-01-02', 'x');
INSERT INTO paper_state(key, value) VALUES ('cash', '9000');
INSERT INTO paper_equity(day, equity, cash) VALUES ('2026-11-01', 10000, 9000);
"""


def test_migrates_old_database_to_owner(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript(OLD)
    con.close()
    st = Storage(db)
    assert st.get_user(user_id=1)["is_admin"] == 1
    assert st.watchlist()[0]["name"] == "SAP" and len(st.alerts()) == 1 and len(st.positions()) == 1
    assert st.paper_state() == {"cash": "9000"} and st.paper_equity()[0]["equity"] == 10000
    other = st.for_user(2)
    assert other.watchlist() == [] and other.alerts() == [] and other.positions() == [] and other.paper_state() == {}
    Storage(db)  # zweites Öffnen ändert nichts mehr
    assert len(Storage(db).watchlist()) == 1


def test_users_are_isolated(tmp_path):
    st = Storage(tmp_path / "t.db")
    a = st.create_user("till", "h")
    b = st.create_user("anna", "h")
    assert st.get_user(user_id=a)["is_admin"] == 1 and st.get_user(user_id=b)["is_admin"] == 0
    sa, sb = st.for_user(a), st.for_user(b)
    sa.add_symbol("SAP.DE")
    sb.add_symbol("SAP.DE", note="Anna")
    pid = sa.add_position({"symbol": "SAP.DE", "quantity": 1, "buy_price": 1, "buy_date": "2026-01-01"})
    aid = sa.add_alert("SAP.DE", "price_above", {"value": 1})
    assert sb.get_position(pid) is None and not sb.remove_position(pid) and not sb.remove_alert(aid)
    assert sb.watchlist()[0]["note"] == "Anna" and sa.watchlist()[0]["note"] == ""
    sb.set_user_setting("risk_profile", "aggressive")
    assert sa.user_settings() == {} and sb.user_settings() == {"risk_profile": "aggressive"}
    sb.save_chart_layout("sap.de", {"lines": [1]})
    assert sa.chart_layout("SAP.DE") is None and sb.chart_layout("SAP.DE")["lines"] == [1]
    assert not st.delete_user(a)  # Admin bleibt
    assert st.delete_user(b) and sb.watchlist() == [] and st.get_user(user_id=b) is None


def test_invites(tmp_path):
    st = Storage(tmp_path / "t.db")
    a = st.create_user("till", "h")
    token = st.create_invite(a, "Anna")
    assert st.check_invite(token)["note"] == "Anna" and st.check_invite("falsch") is None
    b = st.create_user("anna", "h")
    assert st.use_invite(token, b) and st.check_invite(token) is None and not st.use_invite(token, b)
    assert st.invites()[0]["used_by_name"] == "anna"
    t2 = st.create_invite(a, days=-1)
    assert st.check_invite(t2) is None  # abgelaufen


def test_reset_admin_login_keeps_data(tmp_path):
    st = Storage(tmp_path / "t.db")
    a = st.create_user("till", "h")
    st.for_user(a).add_symbol("X")
    assert st.reset_admin_login()
    u = st.get_user(user_id=a)
    assert u["password_hash"] == "" and u["token_version"] == 1 and st.for_user(a).watchlist_symbols() == ["X"]
