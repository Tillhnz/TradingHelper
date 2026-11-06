"""TradeHelper-Backend (FastAPI). Alle Routen liegen unter /api, das Frontend (nginx) reicht sie durch."""

from __future__ import annotations

import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from datetime import date

from . import __version__, alerts, analysis, entry, events, indicators, market, news, notify, paper, portfolio, scheduler
from . import settings_store
from . import updater_client
from .config import Settings
from .config import settings as base_settings
from .report import build_report, send_report
from .security import create_token, hash_password, read_token, verify_password
from .storage import Storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tradehelper")

_storage: Storage | None = None


def get_storage() -> Storage:
    """Datenbank für server-weite Dinge (Anmeldung, Nutzerverwaltung). Nutzerdaten: user_storage."""
    global _storage
    if _storage is None or _storage.path != str(base_settings.db_path):
        _storage = Storage(base_settings.db_path)
    return _storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        st = get_storage()
    except Exception:
        log.exception("Datenbank %s lässt sich nicht öffnen. Ist der Ordner beschreibbar (Benutzer 10001)?",
                      base_settings.db_path)
        raise
    settings_store.apply_overrides(st, base_settings)
    if base_settings.scheduler_enabled:
        scheduler.start(st, base_settings)
    yield
    scheduler.stop()


app = FastAPI(title="TradeHelper", version=__version__, lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json")


# ---------- Anmeldung ----------

def current_user(authorization: str | None = Header(default=None), st: Storage = Depends(get_storage)) -> dict:
    unauthorized = HTTPException(401, "Nicht angemeldet")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized
    data = read_token(authorization[7:], base_settings.secret_key)
    if not data:
        raise unauthorized
    user = st.get_user(user_id=int(data["sub"]))
    if not user or user["token_version"] != data.get("tv") or not user["password_hash"]:
        raise unauthorized
    return user


def user_storage(user: dict = Depends(current_user)) -> Storage:
    """Datenbank, gebunden an den angemeldeten Nutzer: er sieht nur seine eigenen Daten."""
    return get_storage().for_user(user["id"])


def user_cfg(st: Storage = Depends(user_storage)) -> Settings:
    """Einstellungen des angemeldeten Nutzers (server-weite plus persönliche)."""
    return settings_store.for_user(st, base_settings)


def require_admin(user: dict = Depends(current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(403, "Nur der Admin darf das.")
    return user


auth = [Depends(current_user)]
admin_only = [Depends(require_admin)]

_fails: dict[str, list[float]] = {}


def _rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "?"
    now = time.time()
    recent = [t for t in _fails.get(ip, []) if now - t < 600]
    _fails[ip] = recent
    if len(recent) >= 8:
        raise HTTPException(429, "Zu viele Fehlversuche. Bitte in einigen Minuten erneut versuchen.")


def _fail(request: Request) -> None:
    ip = request.client.host if request.client else "?"
    _fails.setdefault(ip, []).append(time.time())


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=200)


class PasswordChange(BaseModel):
    current: str
    new: str = Field(min_length=8, max_length=200)


@app.get("/api/health")
def health(st: Storage = Depends(get_storage)):
    try:
        st.user_count()  # prüft, dass die Datenbank wirklich nutzbar ist (sonst würde ein Update nicht zurückrollen)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Datenbank nicht nutzbar: {exc}") from exc
    return {"status": "ok", "version": __version__}


@app.get("/api/auth/status")
def auth_status(st: Storage = Depends(get_storage)):
    admin = st.admin()
    # Einrichtung nötig: noch kein Konto, oder die Admin-Anmeldung wurde im Terminal zurückgesetzt
    return {"setup_required": st.user_count() == 0 or (admin is not None and not admin["password_hash"])}


@app.post("/api/auth/setup")
def auth_setup(data: Credentials, st: Storage = Depends(get_storage)):
    admin = st.admin()
    if st.user_count() > 0 and not (admin and not admin["password_hash"]):
        raise HTTPException(409, "Es gibt bereits ein Konto. Bitte anmelden.")
    if len(data.password) < 8:
        raise HTTPException(422, "Das Passwort braucht mindestens 8 Zeichen.")
    if admin:  # nach reset-login: Zugangsdaten neu setzen, Daten bleiben
        other = st.get_user(username=data.username.strip())
        if other and other["id"] != admin["id"]:
            raise HTTPException(409, "Diesen Benutzernamen gibt es schon.")
        st.set_password(admin["id"], hash_password(data.password), username=data.username.strip())
        fresh = st.get_user(user_id=admin["id"])
        return {"token": create_token(fresh["id"], fresh["token_version"], base_settings.secret_key)}
    uid = st.create_user(data.username.strip(), hash_password(data.password))
    return {"token": create_token(uid, 0, base_settings.secret_key)}


class Registration(Credentials):
    token: str = Field(min_length=10, max_length=100)


@app.get("/api/auth/invite/{token}")
def invite_check(token: str, request: Request, st: Storage = Depends(get_storage)):
    _rate_limit(request)
    inv = st.check_invite(token)
    if not inv:
        _fail(request)
        raise HTTPException(404, "Diese Einladung ist ungültig, schon benutzt oder abgelaufen.")
    owner = st.get_user(user_id=inv["created_by"])
    return {"valid": True, "invited_by": owner["username"] if owner else None, "expires_at": inv["expires_at"]}


@app.post("/api/auth/register")
def register(data: Registration, request: Request, st: Storage = Depends(get_storage)):
    """Konto über einen Einladungslink anlegen. Neue Nutzer haben eigene Daten und keine Admin-Rechte."""
    _rate_limit(request)
    if not st.check_invite(data.token):
        _fail(request)
        raise HTTPException(404, "Diese Einladung ist ungültig, schon benutzt oder abgelaufen.")
    if len(data.password) < 8:
        raise HTTPException(422, "Das Passwort braucht mindestens 8 Zeichen.")
    if st.get_user(username=data.username.strip()):
        raise HTTPException(409, "Diesen Benutzernamen gibt es schon.")
    uid = st.create_user(data.username.strip(), hash_password(data.password), is_admin=False)
    if not st.use_invite(data.token, uid):  # gleichzeitig benutzt
        st.delete_user(uid)
        raise HTTPException(409, "Diese Einladung wurde gerade schon benutzt.")
    return {"token": create_token(uid, 0, base_settings.secret_key)}


@app.post("/api/auth/login")
def auth_login(data: Credentials, request: Request, st: Storage = Depends(get_storage)):
    _rate_limit(request)
    user = st.get_user(username=data.username.strip())
    if not user or not user["password_hash"] or not verify_password(data.password, user["password_hash"]):
        _fail(request)
        raise HTTPException(401, "Benutzername oder Passwort falsch.")
    return {"token": create_token(user["id"], user["token_version"], base_settings.secret_key)}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return {"id": user["id"], "username": user["username"], "is_admin": bool(user["is_admin"])}


# ---------- Nutzer und Einladungen (nur Admin) ----------

class InviteIn(BaseModel):
    note: str = Field(default="", max_length=80)
    days: int = Field(default=7, ge=1, le=60)


@app.get("/api/users", dependencies=admin_only)
def users_list(st: Storage = Depends(get_storage)):
    return {"users": st.users(), "invites": st.invites()}


@app.post("/api/users/invites", status_code=201)
def invite_create(item: InviteIn, user: dict = Depends(require_admin), st: Storage = Depends(get_storage)):
    """Einladungscode einmalig zurückgeben; die Oberfläche baut daraus den Link."""
    token = st.create_invite(user["id"], item.note.strip(), item.days)
    return {"token": token, "path": f"/einladung/{token}", "days": item.days}


@app.delete("/api/users/invites/{invite_id}", dependencies=admin_only)
def invite_delete(invite_id: int, st: Storage = Depends(get_storage)):
    if not st.delete_invite(invite_id):
        raise HTTPException(404, "Einladung nicht gefunden")
    return {"ok": True}


@app.delete("/api/users/{user_id}", dependencies=admin_only)
def user_delete(user_id: int, st: Storage = Depends(get_storage)):
    """Nutzer mit allen seinen Daten löschen. Der Admin selbst kann nicht gelöscht werden."""
    if not st.delete_user(user_id):
        raise HTTPException(404, "Nutzer nicht gefunden oder Admin")
    return {"ok": True}


@app.post("/api/auth/password")
def change_password(data: PasswordChange, user: dict = Depends(current_user), st: Storage = Depends(get_storage)):
    if not verify_password(data.current, user["password_hash"]):
        raise HTTPException(403, "Das aktuelle Passwort stimmt nicht.")
    st.set_password(user["id"], hash_password(data.new))
    fresh = st.get_user(user_id=user["id"])
    return {"token": create_token(fresh["id"], fresh["token_version"], base_settings.secret_key)}


# ---------- Kurse und Analyse ----------

def _target(currency: str | None, settings: Settings) -> str | None:
    """Gewünschte Anzeigewährung: Parameter, sonst Einstellung. None = Handelswährung."""
    c = currency or settings.display_currency or "native"
    if c == "native":
        return None
    if c not in market.CURRENCIES:
        raise HTTPException(422, f"Währung muss native oder eine von {', '.join(market.CURRENCIES)} sein")
    return c


def _info(symbol: str) -> dict:
    try:
        return market.symbol_info(symbol)
    except market.MarketDataError:
        exchange, currency = market.guess_listing(symbol)
        return {"symbol": symbol.upper(), "name": None, "exchange": exchange, "currency": currency, "type": None}


def _history(symbol: str, period: str, interval: str, target: str | None = None):
    if interval in market.INTRADAY and market.intraday_limit(symbol) and period not in ("1d", "5d"):
        raise HTTPException(422, "Für gettex gibt es Minutenkerzen nur für den letzten Tag oder die letzten 5 Handelstage.")
    try:
        return market.get_history(symbol, period, interval, currency=target)
    except market.MarketDataError as exc:
        raise HTTPException(404, str(exc)) from exc


def _meta(symbol: str, target: str | None, settings: Settings) -> dict:
    info = _info(symbol)
    t = market.last_trade_time(symbol)
    return {
        "ticker": info.get("ticker"), "isin": info.get("isin"), "intraday": market.supports_intraday(symbol), "intraday_limit": market.intraday_limit(symbol),
        "name": info.get("name"), "exchange": info.get("exchange"), "native_currency": info.get("currency"),
        "currency": market.shown_currency(info.get("currency"), target),
        "display_currency": settings.display_currency,
        "delay_min": info.get("delay_min"), "quote_source": info.get("quote_source"),
        "as_of": t,
    }


def _chart_positions(symbol: str, shown: str | None, st: Storage) -> list[dict]:
    """Positionen eines Symbols mit Kursen in der Chart-Währung (Kauf/Verkauf zum Tageskurs, Stopp/Ziel aktuell)."""
    out = []
    for pos in st.positions(symbol):
        ccy = portfolio.position_currency(pos)
        conv = (lambda v, day=None, c=ccy: market.convert_price(v, c, shown, day)) if ccy and shown else (lambda v, day=None: v)
        try:
            out.append({
                "id": pos["id"], "quantity": pos["quantity"], "buy_date": pos["buy_date"], "sell_date": pos["sell_date"],
                "buy_price": conv(pos["buy_price"], pos["buy_date"]), "stop": conv(pos["stop"]),
                "target": conv(pos["target"]),
                "sell_price": conv(pos["sell_price"], pos["sell_date"]) if pos["sell_price"] else None,
                "converted": bool(ccy and shown and ccy != shown),
            })
        except market.MarketDataError:
            continue
    return out


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, 6)


@app.get("/api/quote/{symbol}", dependencies=auth)
def quote(symbol: str):
    try:
        return market.get_quote(symbol).to_dict()
    except market.MarketDataError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/quotes", dependencies=auth)
def quotes(symbols: str, currency: str | None = None, settings: Settings = Depends(user_cfg)):
    """Aktuelle Kurse mehrerer Werte für die Live-Anzeige (wird von der Oberfläche alle paar Sekunden abgefragt)."""
    target = _target(currency, settings)
    syms = [x.strip().upper() for x in symbols.split(",") if x.strip()][:40]

    def one(sym):
        try:
            return market.live(sym, target)
        except Exception as exc:  # noqa: BLE001
            return {"symbol": sym, "error": str(exc)[:120]}

    if not syms:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(syms))) as pool:
        return list(pool.map(one, syms))


@app.get("/api/search", dependencies=auth)
def search(q: str):
    try:
        return market.search(q)
    except market.MarketDataError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/history/{symbol}", dependencies=auth)
def history(symbol: str, period: str = "1y", interval: str = "1d", currency: str | None = None,
            st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    target = _target(currency, settings)
    df = indicators.add_all(_history(symbol, period, interval, target))
    signal_events = events.signal_events(df, analysis.profile_from(settings))
    times = [int(ts.timestamp()) for ts in df.index]
    cols = list(df.columns)
    rows = []
    for t, values in zip(times, df.itertuples(index=False), strict=True):
        row = {"time": int(t)}
        row.update({c: _num(v) for c, v in zip(cols, values, strict=True)})
        rows.append(row)
    meta = _meta(symbol, target, settings)
    if not meta["as_of"] and rows:
        meta["as_of"] = rows[-1]["time"]
    return {"symbol": symbol.upper(), "period": period, "interval": interval, "rows": rows, "events": signal_events,
            "positions": _chart_positions(symbol, meta["currency"], st), **meta}


@app.get("/api/analysis/{symbol}", dependencies=auth)
def analyze(symbol: str, period: str | None = None, interval: str = "1d", with_news: bool = True,
            currency: str | None = None, settings: Settings = Depends(user_cfg)):
    """Ohne period wird der Zeitraum der Anlagestrategie genommen (gleiche Einschätzung wie im Report)."""
    target = _target(currency, settings)
    profile = analysis.profile_from(settings)
    df = _history(symbol, period or profile.period, interval, target)
    try:
        a = analysis.analyze(symbol, df, profile)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    meta = _meta(symbol, target, settings)
    items = news.collect(symbol, settings, meta.get("name")) if with_news else []
    rec = analysis.recommend(a, news.aggregate_sentiment(items))
    return {**a.to_dict(), "recommendation": rec.__dict__, "entry": entry.plan(a, rec, currency=meta["currency"]),
            "news": [n.to_dict() for n in items], "news_sources": news.sources(settings) if with_news else [], **meta}


@app.get("/api/news/market", dependencies=auth)
def get_market_news(limit: int = 30, settings: Settings = Depends(user_cfg)):
    """Allgemeine Wirtschafts- und Börsennachrichten aus den eingestellten Feeds (Startseite)."""
    items = news.market_news(settings, limit=max(1, min(limit, 100)))
    return {"feeds": [n for n, _ in news.parse_feed_list(settings.news_feeds)], "items": [i.to_dict() for i in items]}


@app.get("/api/news/watchlist", dependencies=auth)
def get_watchlist_news(limit: int = 20, per_symbol: int = 4, st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    """Neueste Meldungen zu allen beobachteten und gehaltenen Werten, mit Name des Werts."""
    _sync_watchlist(st)
    rows = st.watchlist()[:40]
    per = max(1, min(per_symbol, 10))

    def one(w):
        return w, news.collect(w["symbol"], settings, w.get("name"), limit=per)

    out = []
    if rows:
        with ThreadPoolExecutor(max_workers=min(6, len(rows))) as pool:
            for w, items in pool.map(one, rows):
                for i in items:
                    out.append({**i.to_dict(), "symbol": w["symbol"], "name": w.get("name"), "ticker": w.get("ticker")})
    out.sort(key=lambda x: x["published"] or "", reverse=True)
    return {"sources": news.sources(settings), "items": out[: max(1, min(limit, 100))]}


@app.get("/api/news/{symbol}", dependencies=auth)
def get_news(symbol: str, limit: int = 25, settings: Settings = Depends(user_cfg)):
    items = news.collect(symbol, settings, _info(symbol).get("name"), limit=max(1, min(limit, 50)))
    return {"symbol": symbol.upper(), "sources": news.sources(settings),
            "sentiment": news.aggregate_sentiment(items), "items": [i.to_dict() for i in items]}


# ---------- Watchlist ----------

def _sync_watchlist(st: Storage) -> None:
    """Werte mit offenen Käufen gehören immer in die Watchlist (und damit in den Morgenreport)."""
    have = set(st.watchlist_symbols())
    for sym in {p["symbol"] for p in st.positions(open_only=True)} - have:
        info = _info(sym)
        st.add_symbol(sym, "", info.get("name"), info.get("exchange"), info.get("currency"), info.get("ticker"))


def _holdings_by_symbol(st: Storage, settings: Settings) -> dict[str, dict]:
    profile = analysis.profile_from(settings)
    groups: dict[str, list] = {}
    for p in st.positions():
        groups.setdefault(p["symbol"], []).append(portfolio.evaluate(p, profile))
    return {sym: portfolio.summarize(items) for sym, items in groups.items()}

class WatchlistIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    note: str = Field(default="", max_length=200)


@app.get("/api/watchlist", dependencies=auth)
def watchlist(st: Storage = Depends(user_storage)):
    return st.watchlist()


@app.get("/api/watchlist/overview", dependencies=auth)
def watchlist_overview(st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    """Kurs, Tagesänderung und technische Einschätzung je Wert (ohne News, damit es schnell bleibt)."""
    _sync_watchlist(st)
    holdings = _holdings_by_symbol(st, settings)
    target = _target(None, settings)
    profile = analysis.profile_from(settings)
    out = []
    for w in st.watchlist():
        sym = w["symbol"]
        if w.get("currency") is None and w.get("exchange") is None:  # Einträge aus älteren Versionen nachtragen
            info = _info(sym)
            st.update_meta(sym, info.get("name"), info.get("exchange"), info.get("currency"))
            w.update(name=info.get("name"), exchange=info.get("exchange"), currency=info.get("currency"))
        row = {"symbol": sym, "ticker": w.get("ticker"), "note": w["note"], "name": w.get("name"), "exchange": w.get("exchange"),
               "native_currency": w.get("currency"), "currency": market.shown_currency(w.get("currency"), target)}
        try:
            df = market.get_history(sym, profile.period, "1d", currency=target)
            a = analysis.analyze(sym, df, profile)
            rec = analysis.recommend(a, None)
            spark = [round(float(x), 4) for x in df["close"].tail(30)]
            row.update(price=a.last_close, change_pct=a.change_pct_1d, action=rec.action, score=rec.combined,
                       rsi=a.metrics.get("rsi"), spark=spark, entry=entry.plan(a, rec, currency=row["currency"])["summary"])
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc)
        h = holdings.get(sym)
        row["holding"] = h if h and h.get("shares") else None
        out.append(row)
    return out


@app.post("/api/watchlist", dependencies=auth, status_code=201)
def watchlist_add(item: WatchlistIn, st: Storage = Depends(user_storage)):
    sym = item.symbol.strip().upper()
    try:
        info = market.symbol_info(sym)
    except market.MarketDataError as exc:
        raise HTTPException(404, f"{sym}: keine Kursdaten gefunden. Wert am besten über die Suche auswählen.") from exc
    st.add_symbol(sym, item.note, info.get("name"), info.get("exchange"), info.get("currency"), info.get("ticker"))
    return {"added": sym, **info}


@app.patch("/api/watchlist/{symbol}", dependencies=auth)
def watchlist_note(symbol: str, item: WatchlistIn, st: Storage = Depends(user_storage)):
    if not st.update_note(symbol, item.note):
        raise HTTPException(404, f"{symbol} ist nicht in der Watchlist")
    return {"ok": True}


@app.delete("/api/watchlist/{symbol}", dependencies=auth)
def watchlist_remove(symbol: str, st: Storage = Depends(user_storage)):
    if st.positions(symbol, open_only=True):
        raise HTTPException(409, f"{symbol.upper()} ist im Depot und bleibt deshalb in der Watchlist.")
    if not st.remove_symbol(symbol):
        raise HTTPException(404, f"{symbol} ist nicht in der Watchlist")
    return {"removed": symbol.upper()}


# ---------- Alarme ----------

class AlertIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    kind: str
    params: dict = Field(default_factory=dict)
    interval: str = "1d"
    once: bool = False
    currency: str = ""  # leer = Handelswährung


class AlertPatch(BaseModel):
    active: bool


INTERVALS = ["5m", "15m", "30m", "1h", "1d", "1wk"]


@app.get("/api/alerts/kinds", dependencies=auth)
def alert_kinds(settings: Settings = Depends(user_cfg)):
    return {"intervals": INTERVALS, "currencies": market.CURRENCIES, "display_currency": settings.display_currency,
            "kinds": [{"name": k.name, "description": k.description, "params": k.params} for k in alerts.KINDS.values()]}


@app.get("/api/alerts", dependencies=auth)
def alert_list(st: Storage = Depends(user_storage)):
    out = []
    for a in st.alerts():
        d = a.to_dict()
        info = _info(a.symbol)
        d["native_currency"] = info.get("currency") if not a.currency else None
        d["name"], d["ticker"] = info.get("name"), info.get("ticker")
        out.append(d)
    return out


@app.post("/api/alerts", dependencies=auth, status_code=201)
def alert_add(item: AlertIn, st: Storage = Depends(user_storage)):
    if item.interval not in INTERVALS:
        raise HTTPException(422, f"Intervall muss eines von {', '.join(INTERVALS)} sein")
    if item.interval in market.INTRADAY and market.intraday_limit(item.symbol):
        raise HTTPException(422, "Für gettex-Werte gibt es Alarme nur auf Tages- oder Wochenkerzen.")
    if item.currency and item.currency not in market.CURRENCIES:
        raise HTTPException(422, f"Währung muss leer oder eine von {', '.join(market.CURRENCIES)} sein")
    try:
        params = alerts.build_params(item.kind, item.params)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    aid = st.add_alert(item.symbol.strip(), item.kind, params, item.interval, item.once, item.currency)
    return st.get_alert(aid).to_dict()


@app.patch("/api/alerts/{alert_id}", dependencies=auth)
def alert_toggle(alert_id: int, data: AlertPatch, st: Storage = Depends(user_storage)):
    if not st.set_alert_active(alert_id, data.active):
        raise HTTPException(404, "Alarm nicht gefunden")
    return st.get_alert(alert_id).to_dict()


@app.delete("/api/alerts/{alert_id}", dependencies=auth)
def alert_remove(alert_id: int, st: Storage = Depends(user_storage)):
    if not st.remove_alert(alert_id):
        raise HTTPException(404, "Alarm nicht gefunden")
    return {"removed": alert_id}


@app.post("/api/alerts/check", dependencies=auth)
def alert_check(send: bool = True, st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    return {"fired": alerts.check_all(st, settings, send=send)}


@app.get("/api/alerts/log", dependencies=auth)
def alert_log(limit: int = 50, st: Storage = Depends(user_storage)):
    rows = st.alert_log(min(limit, 500))
    for r in rows:
        info = _info(r["symbol"])
        r["name"], r["ticker"] = info.get("name"), info.get("ticker")
    return rows


# ---------- Depot (erfasste Käufe) ----------

class PositionIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    quantity: float = Field(gt=0)
    buy_price: float = Field(gt=0)
    buy_date: date
    fees: float = Field(default=0, ge=0)
    currency: str = ""
    stop: float | None = Field(default=None, gt=0)
    target: float | None = Field(default=None, gt=0)
    note: str = Field(default="", max_length=300)
    trail_pct: float | None = Field(default=None, ge=0.5, le=50)  # mitlaufender Stopp in Prozent
    create_alerts: bool = False


class PositionPatch(BaseModel):
    quantity: float | None = Field(default=None, gt=0)
    buy_price: float | None = Field(default=None, gt=0)
    buy_date: date | None = None
    fees: float | None = Field(default=None, ge=0)
    stop: float | None = Field(default=None, ge=0)  # 0 = Stopp entfernen
    target: float | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=300)
    sell_price: float | None = Field(default=None, gt=0)
    sell_date: date | None = None
    sell_fees: float | None = Field(default=None, ge=0)
    trail_pct: float | None = Field(default=None, ge=0, le=50)  # 0 = nicht mitlaufen lassen
    reopen: bool = False


def _check_position(d: dict) -> None:
    if d.get("currency") and d["currency"] not in market.CURRENCIES:
        raise HTTPException(422, f"Währung muss leer oder eine von {', '.join(market.CURRENCIES)} sein")
    for key in ("buy_date", "sell_date"):
        if d.get(key) and date.fromisoformat(d[key]) > date.today():
            raise HTTPException(422, "Datum liegt in der Zukunft")
    if d.get("stop") and d.get("target") and d["stop"] >= d["target"]:
        raise HTTPException(422, "Der Stopp muss unter dem Ziel liegen")
    if d.get("sell_date") and d.get("buy_date") and d["sell_date"] < d["buy_date"]:
        raise HTTPException(422, "Verkauf liegt vor dem Kauf")


def _total_currency(settings: Settings) -> str:
    return settings.display_currency if settings.display_currency in market.CURRENCIES else "EUR"


@app.get("/api/positions", dependencies=auth)
def positions_list(st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    profile = analysis.profile_from(settings)
    items = [portfolio.evaluate(p, profile) for p in st.positions()]
    total_ccy = _total_currency(settings)
    totals = {"currency": total_ccy, "invested": 0.0, "value": 0.0, "pl": 0.0, "realized": 0.0}
    for it in items:
        ccy = it["display_currency"]
        try:
            conv = (lambda v, c=ccy: market.convert_price(v, c, total_ccy)) if ccy else (lambda v: v)
            if it["closed"]:
                totals["realized"] += conv(it["pl"])
            elif it.get("value") is not None:
                totals["invested"] += conv(it["invested"])
                totals["value"] += conv(it["value"])
        except market.MarketDataError:
            continue
    totals["pl"] = totals["value"] - totals["invested"]
    totals["pl_pct"] = round(totals["pl"] / totals["invested"] * 100, 2) if totals["invested"] else None
    totals = {k: round(v, 2) if isinstance(v, float) else v for k, v in totals.items()}
    return {"items": items, "totals": totals}


@app.get("/api/holdings/{symbol}", dependencies=auth)
def holding(symbol: str, st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    """Alles, was du von einem Wert besitzt oder besessen hast: Käufe mit Auswertung und Zusammenfassung."""
    profile = analysis.profile_from(settings)
    items = [portfolio.evaluate(p, profile) for p in st.positions(symbol)]
    return {"symbol": symbol.upper(), "items": items, "summary": portfolio.summarize(items)}


@app.get("/api/positions/history", dependencies=auth)
def positions_history(st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    return portfolio.history(st.positions(), _total_currency(settings))


@app.post("/api/positions", dependencies=auth, status_code=201)
def position_add(item: PositionIn, st: Storage = Depends(user_storage)):
    data = item.model_dump()
    create_alerts = data.pop("create_alerts")
    data["symbol"] = data["symbol"].strip().upper()
    data["buy_date"] = data["buy_date"].isoformat()
    _check_position(data)
    if data["stop"] and data["stop"] >= data["buy_price"]:
        raise HTTPException(422, "Der Stopp muss unter dem Kaufkurs liegen")
    pid = st.add_position(data)
    _sync_watchlist(st)
    created = []
    if create_alerts:
        # Ein mitlaufender Stopp ändert sich; den meldet die Depot-Prüfung statt eines festen Kursalarms
        if data["stop"] and not data.get("trail_pct"):
            created.append(st.add_alert(data["symbol"], "price_below", {"value": data["stop"]}, "1d", True, data["currency"]))
        if data["target"]:
            created.append(st.add_alert(data["symbol"], "price_above", {"value": data["target"]}, "1d", True,
                                        data["currency"]))
    return {**st.get_position(pid), "alerts": created}


@app.patch("/api/positions/{pos_id}", dependencies=auth)
def position_update(pos_id: int, item: PositionPatch, st: Storage = Depends(user_storage)):
    current = st.get_position(pos_id)
    if not current:
        raise HTTPException(404, "Position nicht gefunden")
    data = {k: v for k, v in item.model_dump(exclude_unset=True).items() if k != "reopen"}
    for key in ("buy_date", "sell_date"):
        if isinstance(data.get(key), date):
            data[key] = data[key].isoformat()
    for key in ("stop", "target", "trail_pct"):
        if data.get(key) == 0:
            data[key] = None
    if item.reopen:
        data.update(sell_price=None, sell_date=None, sell_fees=0)
    elif ("sell_price" in data) != ("sell_date" in data) and not current["sell_date"]:
        raise HTTPException(422, "Für einen Verkauf bitte Kurs und Datum angeben")
    _check_position({**current, **data})
    st.update_position(pos_id, data)
    _move_alerts(st, current, data)
    return st.get_position(pos_id)


def _move_alerts(st: Storage, old: dict, new: dict) -> None:
    """Kursalarme, die zum alten Stopp bzw. Ziel der Position gehören, auf den neuen Wert umstellen."""
    for key, kind in (("stop", "price_below"), ("target", "price_above")):
        if key not in new or not old.get(key) or not new[key] or new[key] == old[key]:
            continue
        for al in st.alerts(active_only=True):
            if al.symbol == old["symbol"] and al.kind == kind and abs(float(al.params.get("value", 0)) - old[key]) < 1e-6:
                st.set_alert_params(al.id, {**al.params, "value": new[key]})


@app.delete("/api/positions/{pos_id}", dependencies=auth)
def position_remove(pos_id: int, st: Storage = Depends(user_storage)):
    if not st.remove_position(pos_id):
        raise HTTPException(404, "Position nicht gefunden")
    return {"removed": pos_id}


# ---------- Chart-Arbeitsplatz ----------

class ChartPoint(BaseModel):
    time: int
    price: float


class Drawing(BaseModel):
    id: str = Field(max_length=40)
    kind: str = Field(pattern="^(hline|trend|ray|fib)$")
    points: list[ChartPoint] = Field(min_length=1, max_length=2)
    color: str = Field(default="#f2b84b", pattern="^#[0-9a-fA-F]{6}$")
    label: str = Field(default="", max_length=60)


class Indicator(BaseModel):
    id: str = Field(max_length=40)
    kind: str = Field(pattern="^(sma|ema|bb|rsi|macd|volume)$")
    params: dict[str, float] = Field(default_factory=dict)
    color: str = Field(default="#6fd3c3", pattern="^#[0-9a-fA-F]{6}$")


class ChartLayout(BaseModel):
    type: str = Field(default="candles", pattern="^(area|line|candles|bars)$")
    period: str = Field(default="6mo", max_length=5)
    interval: str = Field(default="1d", max_length=4)
    indicators: list[Indicator] = Field(default_factory=list, max_length=12)
    drawings: list[Drawing] = Field(default_factory=list, max_length=80)


@app.get("/api/charts", dependencies=auth)
def charts_list(st: Storage = Depends(user_storage)):
    names = {w["symbol"]: w for w in st.watchlist()}
    return [{**c, "name": names.get(c["symbol"], {}).get("name"), "ticker": names.get(c["symbol"], {}).get("ticker")}
            for c in st.chart_layouts()]


@app.get("/api/charts/{symbol}", dependencies=auth)
def chart_get(symbol: str, st: Storage = Depends(user_storage)):
    """Gespeicherte Zeichnungen und Kennlinien eines Werts (oder eine leere Vorlage)."""
    return st.chart_layout(symbol) or {**ChartLayout(indicators=[
        Indicator(id="sma50", kind="sma", params={"period": 50}, color="#f2b84b"),
        Indicator(id="sma200", kind="sma", params={"period": 200}, color="#8d9eb0"),
        Indicator(id="vol", kind="volume")]).model_dump(), "updated_at": None}


@app.put("/api/charts/{symbol}", dependencies=auth)
def chart_save(symbol: str, layout: ChartLayout, st: Storage = Depends(user_storage)):
    st.save_chart_layout(symbol, layout.model_dump())
    return st.chart_layout(symbol)


@app.delete("/api/charts/{symbol}", dependencies=auth)
def chart_delete(symbol: str, st: Storage = Depends(user_storage)):
    st.delete_chart_layout(symbol)
    return {"ok": True}


# ---------- Morgenreport ----------

@app.get("/api/report", dependencies=auth)
def report(st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    _sync_watchlist(st)
    return build_report(st, settings).to_dict()


@app.get("/api/reports/latest", dependencies=auth)
def report_latest(st: Storage = Depends(user_storage)):
    rep = st.get_report()
    if not rep:
        raise HTTPException(404, "Noch kein Morgenbericht verschickt.")
    return rep


@app.get("/api/reports/{report_id}", dependencies=auth)
def report_get(report_id: int, st: Storage = Depends(user_storage)):
    rep = st.get_report(report_id)
    if not rep:
        raise HTTPException(404, "Bericht nicht gefunden.")
    return rep


@app.post("/api/report/send", dependencies=auth)
def report_send(st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    if not settings.ntfy_topic:
        raise HTTPException(400, "Kein ntfy-Topic hinterlegt (Einstellungen → Benachrichtigungen).")
    rep = send_report(st, settings)
    return {"sent": True, "entries": len(rep.entries)}


# ---------- Einstellungen ----------

@app.get("/api/settings")
def get_settings_route(user: dict = Depends(current_user), st: Storage = Depends(user_storage),
                       settings: Settings = Depends(user_cfg)):
    admin = bool(user["is_admin"])
    return {"fields": settings_store.describe(st, settings, admin), "next_runs": scheduler.next_runs(), "is_admin": admin}


@app.put("/api/settings")
def save_settings(values: dict, user: dict = Depends(current_user), st: Storage = Depends(user_storage),
                  settings: Settings = Depends(user_cfg)):
    admin = bool(user["is_admin"])
    try:
        changed = settings_store.save(st, settings, values, base_settings, admin)
    except settings_store.SettingError as exc:
        raise HTTPException(422, str(exc)) from exc
    if set(changed) & settings_store.SCHEDULE_KEYS:
        scheduler.replan(get_storage(), base_settings)
    return {"changed": changed, "fields": settings_store.describe(st, settings, admin), "next_runs": scheduler.next_runs(),
            "is_admin": admin}


@app.post("/api/settings/test-notify", dependencies=auth)
def test_notify(settings: Settings = Depends(user_cfg)):
    if not settings.ntfy_topic:
        raise HTTPException(400, "Bitte zuerst ein ntfy-Topic eintragen und speichern.")
    if not notify.send(settings, "TradeHelper Test", "Benachrichtigungen funktionieren ✅", tags=["white_check_mark"]):
        raise HTTPException(502, "Versand fehlgeschlagen. Adresse, Topic und Token prüfen.")
    return {"ok": True}


# ---------- Schattendepot ----------

@app.get("/api/paper", dependencies=auth)
def paper_view(st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    return {**paper.view(st, settings), "enabled": settings.paper_enabled,
            "next_run": scheduler.next_runs().get("paper_run")}


@app.post("/api/paper/run", dependencies=auth)
def paper_run(st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    """Startet das Schattendepot (falls nötig) und handelt sofort nach den aktuellen Einschätzungen."""
    if not st.watchlist():
        raise HTTPException(400, "Die Watchlist ist leer – erst Werte hinzufügen.")
    return paper.run_live(st, settings, push=False)


@app.post("/api/paper/reset", dependencies=auth)
def paper_reset(st: Storage = Depends(user_storage)):
    """Alles löschen und mit dem eingestellten Startkapital neu beginnen (der Rückblick bleibt)."""
    st.reset_paper()
    return {"ok": True}


@app.get("/api/paper/backtest", dependencies=auth)
def paper_backtest(st: Storage = Depends(user_storage)):
    return {**paper.backtest_status(st.uid), "result": paper.last_backtest(st)}


@app.post("/api/paper/backtest", dependencies=auth)
def paper_backtest_start(st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    if not st.watchlist():
        raise HTTPException(400, "Die Watchlist ist leer – erst Werte hinzufügen.")
    paper.start_backtest(st, settings)
    return paper.backtest_status(st.uid)


# ---------- Administration ----------

@app.get("/api/admin/status", dependencies=admin_only)
def admin_status(st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    checks = [
        {"label": "Benachrichtigungen (ntfy)", "ok": bool(settings.ntfy_topic),
         "text": f"{settings.ntfy_url}/{settings.ntfy_topic}" if settings.ntfy_topic else "kein Topic hinterlegt"},
        {"label": "Nachrichten", "ok": bool(news.sources(settings)),
         "text": (", ".join(news.sources(settings)) or "alle Quellen aus")
         + f" · {len(news.parse_feed_list(settings.news_feeds))} Marktfeeds"},
    ]
    try:
        market.get_history("^GSPC", "5d", "1d")
        checks.append({"label": "Kursdaten (Yahoo)", "ok": True, "text": "erreichbar"})
    except market.MarketDataError as exc:
        checks.append({"label": "Kursdaten (Yahoo)", "ok": False, "text": str(exc)[:160]})
    try:
        updater_client.call("GET", "/status", timeout=5)
        checks.append({"label": "Update-Dienst", "ok": True, "text": "läuft"})
    except HTTPException as exc:
        checks.append({"label": "Update-Dienst", "ok": False, "text": exc.detail})
    return {
        "version": __version__,
        "checks": checks,
        "next_runs": scheduler.next_runs(),
        "counts": {"watchlist": len(st.watchlist()), "alerts": len(st.alerts(active_only=True)), "users": st.user_count()},
    }


@app.get("/api/admin/update", dependencies=admin_only)
def update_status(check: bool = False):
    return updater_client.call("GET", "/status" + ("?check=1" if check else ""), timeout=120 if check else 30)


@app.post("/api/admin/update", dependencies=admin_only, status_code=202)
def start_update():
    return updater_client.call("POST", "/update")


@app.get("/api/admin/backups", dependencies=admin_only)
def list_backups():
    return updater_client.call("GET", "/backups")


@app.post("/api/admin/backups", dependencies=admin_only, status_code=201)
def create_backup():
    return updater_client.call("POST", "/backups", timeout=120)


# ---------- Version (Hinweis in der Seitenleiste) ----------

_ver_lock = threading.Lock()
_ver = {"behind": None, "checked": 0.0, "running": False}


def _refresh_version() -> None:
    try:
        behind = updater_client.call("GET", "/status?check=1", timeout=120).get("behind")
        result = bool(behind) if behind is not None else None
    except Exception:  # noqa: BLE001
        result = None
    with _ver_lock:
        _ver.update(behind=result, checked=time.time(), running=False)


@app.get("/api/version", dependencies=auth)
def version():
    with _ver_lock:
        stale = time.time() - _ver["checked"] > 3600 and not _ver["running"]
        if stale:
            _ver["running"] = True
        behind = _ver["behind"]
    if stale:
        threading.Thread(target=_refresh_version, daemon=True).start()
    return {"version": __version__, "update_available": behind}
