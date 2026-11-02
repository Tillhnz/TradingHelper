"""REST-API (FastAPI). Doku unter /docs, Chart-Ansicht unter /chart/{symbol}."""

from __future__ import annotations

import math
from importlib import resources

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import __version__, alerts, analysis, indicators, market, news
from .config import Settings, get_settings
from .report import build_report
from .storage import Storage


def get_storage() -> Storage:
    return Storage(get_settings().db_path)


def require_key(x_api_key: str | None = Header(default=None), settings: Settings = Depends(get_settings)):
    if settings.api_key and x_api_key != settings.api_key:
        raise HTTPException(401, "Ungültiger oder fehlender X-API-Key")


app = FastAPI(title="TradeHelper", version=__version__)
protected = [Depends(require_key)]


class WatchlistIn(BaseModel):
    symbol: str
    note: str = ""


class AlertIn(BaseModel):
    symbol: str
    kind: str
    params: dict = Field(default_factory=dict)
    interval: str = "1d"
    once: bool = False


def _history(symbol: str, period: str, interval: str):
    try:
        return market.get_history(symbol, period, interval)
    except market.MarketDataError as exc:
        raise HTTPException(404, str(exc)) from exc


def _clean(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@app.get("/quote/{symbol}", dependencies=protected)
def quote(symbol: str):
    try:
        return market.get_quote(symbol).to_dict()
    except market.MarketDataError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/history/{symbol}", dependencies=protected)
def history(symbol: str, period: str = "1y", interval: str = "1d", indicators_: bool = Query(True, alias="indicators")):
    df = _history(symbol, period, interval)
    if indicators_:
        df = indicators.add_all(df)
    df = df.reset_index()
    df["time"] = df.iloc[:, 0].astype("int64") // 10**9
    df = df.drop(columns=df.columns[0])
    rows = [{k: _clean(float(v)) if k != "time" else int(v) for k, v in r.items()}
            for r in df.to_dict(orient="records")]
    return {"symbol": symbol.upper(), "period": period, "interval": interval, "rows": rows}


@app.get("/analysis/{symbol}", dependencies=protected)
def analyze(symbol: str, period: str = "1y", interval: str = "1d", with_news: bool = True,
            settings: Settings = Depends(get_settings)):
    df = _history(symbol, period, interval)
    try:
        a = analysis.analyze(symbol, df)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    items = news.fetch_news(symbol, settings.finnhub_api_key, settings.news_lookback_days) if with_news else []
    rec = analysis.recommend(a, news.aggregate_sentiment(items))
    return {**a.to_dict(), "recommendation": rec.__dict__, "news": [n.to_dict() for n in items]}


@app.get("/news/{symbol}", dependencies=protected)
def get_news(symbol: str, settings: Settings = Depends(get_settings)):
    if not settings.finnhub_api_key:
        raise HTTPException(503, "TH_FINNHUB_API_KEY ist nicht gesetzt")
    items = news.fetch_news(symbol, settings.finnhub_api_key, settings.news_lookback_days, limit=25)
    return {
        "symbol": symbol.upper(),
        "sentiment": news.aggregate_sentiment(items),
        "items": [i.to_dict() for i in items],
    }


@app.get("/watchlist", dependencies=protected)
def watchlist(storage: Storage = Depends(get_storage)):
    return storage.watchlist()


@app.post("/watchlist", dependencies=protected, status_code=201)
def watchlist_add(item: WatchlistIn, storage: Storage = Depends(get_storage)):
    storage.add_symbol(item.symbol, item.note)
    return {"added": item.symbol.upper()}


@app.delete("/watchlist/{symbol}", dependencies=protected)
def watchlist_remove(symbol: str, storage: Storage = Depends(get_storage)):
    if not storage.remove_symbol(symbol):
        raise HTTPException(404, f"{symbol} nicht in der Watchlist")
    return {"removed": symbol.upper()}


@app.get("/alerts/kinds")
def alert_kinds():
    return {k.name: {"description": k.description, "params": k.params} for k in alerts.KINDS.values()}


@app.get("/alerts", dependencies=protected)
def alert_list(storage: Storage = Depends(get_storage)):
    return [a.to_dict() for a in storage.alerts()]


@app.post("/alerts", dependencies=protected, status_code=201)
def alert_add(item: AlertIn, storage: Storage = Depends(get_storage)):
    try:
        params = alerts.build_params(item.kind, item.params)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    aid = storage.add_alert(item.symbol, item.kind, params, item.interval, item.once)
    return storage.get_alert(aid).to_dict()


@app.delete("/alerts/{alert_id}", dependencies=protected)
def alert_remove(alert_id: int, storage: Storage = Depends(get_storage)):
    if not storage.remove_alert(alert_id):
        raise HTTPException(404, "Alarm nicht gefunden")
    return {"removed": alert_id}


@app.post("/alerts/check", dependencies=protected)
def alert_check(send: bool = True, storage: Storage = Depends(get_storage), settings: Settings = Depends(get_settings)):
    return {"fired": alerts.check_all(storage, settings, send=send)}


@app.get("/alerts/log", dependencies=protected)
def alert_log(limit: int = 50, storage: Storage = Depends(get_storage)):
    return storage.alert_log(limit)


@app.get("/report", dependencies=protected)
def report(storage: Storage = Depends(get_storage), settings: Settings = Depends(get_settings)):
    return build_report(storage, settings).to_dict()


@app.get("/chart/{symbol}", response_class=HTMLResponse)
def chart(symbol: str):
    html = resources.files("tradehelper").joinpath("static/chart.html").read_text(encoding="utf-8")
    return html.replace("__SYMBOL__", symbol.upper())


@app.get("/", response_class=HTMLResponse)
def index():
    return ('<meta name=viewport content="width=device-width"><body style="font-family:system-ui;padding:16px">'
            '<h2>TradeHelper</h2><p><a href="/docs">API-Doku</a> · <a href="/chart/AAPL">Chart-Beispiel</a></p>')
