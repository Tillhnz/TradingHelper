"""TradeHelper-Backend (FastAPI). Alle Routen liegen unter /api, das Frontend (nginx) reicht sie durch."""

from __future__ import annotations

import logging
import math
import threading
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from . import __version__, alerts, analysis, entry, indicators, market, news, notify, scheduler, settings_store
from . import updater_client
from .config import settings
from .report import build_report, send_report
from .security import create_token, hash_password, read_token, verify_password
from .storage import Storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tradehelper")

_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None or _storage.path != str(settings.db_path):
        _storage = Storage(settings.db_path)
    return _storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        st = get_storage()
    except Exception:
        log.exception("Datenbank %s lässt sich nicht öffnen. Ist der Ordner beschreibbar (Benutzer 10001)?", settings.db_path)
        raise
    settings_store.apply_overrides(st, settings)
    if settings.scheduler_enabled:
        scheduler.start(st, settings)
    yield
    scheduler.stop()


app = FastAPI(title="TradeHelper", version=__version__, lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json")


# ---------- Anmeldung ----------

def current_user(authorization: str | None = Header(default=None), st: Storage = Depends(get_storage)) -> dict:
    unauthorized = HTTPException(401, "Nicht angemeldet")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise unauthorized
    data = read_token(authorization[7:], settings.secret_key)
    if not data:
        raise unauthorized
    user = st.get_user(user_id=int(data["sub"]))
    if not user or user["token_version"] != data.get("tv"):
        raise unauthorized
    return user


auth = [Depends(current_user)]

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
    return {"setup_required": st.user_count() == 0}


@app.post("/api/auth/setup")
def auth_setup(data: Credentials, st: Storage = Depends(get_storage)):
    if st.user_count() > 0:
        raise HTTPException(409, "Es gibt bereits ein Konto. Bitte anmelden.")
    if len(data.password) < 8:
        raise HTTPException(422, "Das Passwort braucht mindestens 8 Zeichen.")
    uid = st.create_user(data.username.strip(), hash_password(data.password))
    return {"token": create_token(uid, 0, settings.secret_key)}


@app.post("/api/auth/login")
def auth_login(data: Credentials, request: Request, st: Storage = Depends(get_storage)):
    _rate_limit(request)
    user = st.get_user(username=data.username.strip())
    if not user or not verify_password(data.password, user["password_hash"]):
        _fail(request)
        raise HTTPException(401, "Benutzername oder Passwort falsch.")
    return {"token": create_token(user["id"], user["token_version"], settings.secret_key)}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return {"id": user["id"], "username": user["username"]}


@app.post("/api/auth/password")
def change_password(data: PasswordChange, user: dict = Depends(current_user), st: Storage = Depends(get_storage)):
    if not verify_password(data.current, user["password_hash"]):
        raise HTTPException(403, "Das aktuelle Passwort stimmt nicht.")
    st.set_password(user["id"], hash_password(data.new))
    fresh = st.get_user(user_id=user["id"])
    return {"token": create_token(fresh["id"], fresh["token_version"], settings.secret_key)}


# ---------- Kurse und Analyse ----------

def _target(currency: str | None) -> str | None:
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
    try:
        return market.get_history(symbol, period, interval, currency=target)
    except market.MarketDataError as exc:
        raise HTTPException(404, str(exc)) from exc


def _meta(symbol: str, target: str | None) -> dict:
    info = _info(symbol)
    return {
        "name": info.get("name"), "exchange": info.get("exchange"), "native_currency": info.get("currency"),
        "currency": market.shown_currency(info.get("currency"), target),
        "display_currency": settings.display_currency,
    }


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


@app.get("/api/search", dependencies=auth)
def search(q: str):
    try:
        return market.search(q)
    except market.MarketDataError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.get("/api/history/{symbol}", dependencies=auth)
def history(symbol: str, period: str = "1y", interval: str = "1d", currency: str | None = None):
    target = _target(currency)
    df = indicators.add_all(_history(symbol, period, interval, target))
    times = [int(ts.timestamp()) for ts in df.index]
    cols = list(df.columns)
    rows = []
    for t, values in zip(times, df.itertuples(index=False), strict=True):
        row = {"time": int(t)}
        row.update({c: _num(v) for c, v in zip(cols, values, strict=True)})
        rows.append(row)
    return {"symbol": symbol.upper(), "period": period, "interval": interval, "rows": rows, **_meta(symbol, target)}


@app.get("/api/analysis/{symbol}", dependencies=auth)
def analyze(symbol: str, period: str | None = None, interval: str = "1d", with_news: bool = True,
            currency: str | None = None):
    """Ohne period wird der Zeitraum der Anlagestrategie genommen (gleiche Einschätzung wie im Report)."""
    target = _target(currency)
    profile = analysis.profile_from(settings)
    df = _history(symbol, period or profile.period, interval, target)
    try:
        a = analysis.analyze(symbol, df, profile)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    items = news.fetch_news(symbol, settings.finnhub_api_key, settings.news_lookback_days) if with_news else []
    rec = analysis.recommend(a, news.aggregate_sentiment(items))
    meta = _meta(symbol, target)
    return {**a.to_dict(), "recommendation": rec.__dict__, "entry": entry.plan(a, rec, currency=meta["currency"]),
            "news": [n.to_dict() for n in items], **meta}


@app.get("/api/news/{symbol}", dependencies=auth)
def get_news(symbol: str):
    if not settings.finnhub_api_key:
        raise HTTPException(503, "Kein Finnhub-Schlüssel hinterlegt (Einstellungen → Nachrichten).")
    items = news.fetch_news(symbol, settings.finnhub_api_key, settings.news_lookback_days, limit=25)
    return {"symbol": symbol.upper(), "sentiment": news.aggregate_sentiment(items), "items": [i.to_dict() for i in items]}


# ---------- Watchlist ----------

class WatchlistIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    note: str = Field(default="", max_length=200)


@app.get("/api/watchlist", dependencies=auth)
def watchlist(st: Storage = Depends(get_storage)):
    return st.watchlist()


@app.get("/api/watchlist/overview", dependencies=auth)
def watchlist_overview(st: Storage = Depends(get_storage)):
    """Kurs, Tagesänderung und technische Einschätzung je Wert (ohne News, damit es schnell bleibt)."""
    target = _target(None)
    profile = analysis.profile_from(settings)
    out = []
    for w in st.watchlist():
        sym = w["symbol"]
        if w.get("currency") is None and w.get("exchange") is None:  # Einträge aus älteren Versionen nachtragen
            info = _info(sym)
            st.update_meta(sym, info.get("name"), info.get("exchange"), info.get("currency"))
            w.update(name=info.get("name"), exchange=info.get("exchange"), currency=info.get("currency"))
        row = {"symbol": sym, "note": w["note"], "name": w.get("name"), "exchange": w.get("exchange"),
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
        out.append(row)
    return out


@app.post("/api/watchlist", dependencies=auth, status_code=201)
def watchlist_add(item: WatchlistIn, st: Storage = Depends(get_storage)):
    sym = item.symbol.strip().upper()
    try:
        info = market.symbol_info(sym)
    except market.MarketDataError as exc:
        raise HTTPException(404, f"{sym}: keine Kursdaten gefunden. Wert am besten über die Suche auswählen.") from exc
    st.add_symbol(sym, item.note, info.get("name"), info.get("exchange"), info.get("currency"))
    return {"added": sym, **info}


@app.patch("/api/watchlist/{symbol}", dependencies=auth)
def watchlist_note(symbol: str, item: WatchlistIn, st: Storage = Depends(get_storage)):
    if not st.update_note(symbol, item.note):
        raise HTTPException(404, f"{symbol} ist nicht in der Watchlist")
    return {"ok": True}


@app.delete("/api/watchlist/{symbol}", dependencies=auth)
def watchlist_remove(symbol: str, st: Storage = Depends(get_storage)):
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
def alert_kinds():
    return {"intervals": INTERVALS, "currencies": market.CURRENCIES, "display_currency": settings.display_currency,
            "kinds": [{"name": k.name, "description": k.description, "params": k.params} for k in alerts.KINDS.values()]}


@app.get("/api/alerts", dependencies=auth)
def alert_list(st: Storage = Depends(get_storage)):
    out = []
    for a in st.alerts():
        d = a.to_dict()
        d["native_currency"] = _info(a.symbol).get("currency") if not a.currency else None
        out.append(d)
    return out


@app.post("/api/alerts", dependencies=auth, status_code=201)
def alert_add(item: AlertIn, st: Storage = Depends(get_storage)):
    if item.interval not in INTERVALS:
        raise HTTPException(422, f"Intervall muss eines von {', '.join(INTERVALS)} sein")
    if item.currency and item.currency not in market.CURRENCIES:
        raise HTTPException(422, f"Währung muss leer oder eine von {', '.join(market.CURRENCIES)} sein")
    try:
        params = alerts.build_params(item.kind, item.params)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    aid = st.add_alert(item.symbol.strip(), item.kind, params, item.interval, item.once, item.currency)
    return st.get_alert(aid).to_dict()


@app.patch("/api/alerts/{alert_id}", dependencies=auth)
def alert_toggle(alert_id: int, data: AlertPatch, st: Storage = Depends(get_storage)):
    if not st.set_alert_active(alert_id, data.active):
        raise HTTPException(404, "Alarm nicht gefunden")
    return st.get_alert(alert_id).to_dict()


@app.delete("/api/alerts/{alert_id}", dependencies=auth)
def alert_remove(alert_id: int, st: Storage = Depends(get_storage)):
    if not st.remove_alert(alert_id):
        raise HTTPException(404, "Alarm nicht gefunden")
    return {"removed": alert_id}


@app.post("/api/alerts/check", dependencies=auth)
def alert_check(send: bool = True, st: Storage = Depends(get_storage)):
    return {"fired": alerts.check_all(st, settings, send=send)}


@app.get("/api/alerts/log", dependencies=auth)
def alert_log(limit: int = 50, st: Storage = Depends(get_storage)):
    return st.alert_log(min(limit, 500))


# ---------- Morgenreport ----------

@app.get("/api/report", dependencies=auth)
def report(st: Storage = Depends(get_storage)):
    return build_report(st, settings).to_dict()


@app.post("/api/report/send", dependencies=auth)
def report_send(st: Storage = Depends(get_storage)):
    if not settings.ntfy_topic:
        raise HTTPException(400, "Kein ntfy-Topic hinterlegt (Einstellungen → Benachrichtigungen).")
    rep = send_report(st, settings)
    return {"sent": True, "entries": len(rep.entries)}


# ---------- Einstellungen ----------

@app.get("/api/settings", dependencies=auth)
def get_settings_route(st: Storage = Depends(get_storage)):
    return {"fields": settings_store.describe(st, settings), "next_runs": scheduler.next_runs()}


@app.put("/api/settings", dependencies=auth)
def save_settings(values: dict, st: Storage = Depends(get_storage)):
    try:
        changed = settings_store.save(st, settings, values)
    except settings_store.SettingError as exc:
        raise HTTPException(422, str(exc)) from exc
    if set(changed) & settings_store.SCHEDULE_KEYS:
        scheduler.replan(st, settings)
    return {"changed": changed, "fields": settings_store.describe(st, settings), "next_runs": scheduler.next_runs()}


@app.post("/api/settings/test-notify", dependencies=auth)
def test_notify():
    if not settings.ntfy_topic:
        raise HTTPException(400, "Bitte zuerst ein ntfy-Topic eintragen und speichern.")
    if not notify.send(settings, "TradeHelper Test", "Benachrichtigungen funktionieren ✅", tags=["white_check_mark"]):
        raise HTTPException(502, "Versand fehlgeschlagen. Adresse, Topic und Token prüfen.")
    return {"ok": True}


# ---------- Administration ----------

@app.get("/api/admin/status", dependencies=auth)
def admin_status(st: Storage = Depends(get_storage)):
    checks = [
        {"label": "Benachrichtigungen (ntfy)", "ok": bool(settings.ntfy_topic),
         "text": f"{settings.ntfy_url}/{settings.ntfy_topic}" if settings.ntfy_topic else "kein Topic hinterlegt"},
        {"label": "Nachrichten (Finnhub)", "ok": bool(settings.finnhub_api_key),
         "text": "Schlüssel hinterlegt" if settings.finnhub_api_key else "kein Schlüssel, Empfehlungen ohne News"},
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
        "counts": {"watchlist": len(st.watchlist()), "alerts": len(st.alerts(active_only=True))},
    }


@app.get("/api/admin/update", dependencies=auth)
def update_status(check: bool = False):
    return updater_client.call("GET", "/status" + ("?check=1" if check else ""), timeout=120 if check else 30)


@app.post("/api/admin/update", dependencies=auth, status_code=202)
def start_update():
    return updater_client.call("POST", "/update")


@app.get("/api/admin/backups", dependencies=auth)
def list_backups():
    return updater_client.call("GET", "/backups")


@app.post("/api/admin/backups", dependencies=auth, status_code=201)
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
