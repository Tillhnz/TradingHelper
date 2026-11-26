"""Selbstlernendes Modell: lernt aus Kursverläufen, Marktumfeld, Konjunkturzahlen und Stimmung, wann Halten, Kaufen
oder Verkaufen besser gewesen wäre – und überprüft seine eigenen Entscheidungen.

Was das Modell vorhersagt
    Für jeden Wert und Horizont (kurz 5, mittel 20, lang 60 Handelstage) drei Wahrscheinlichkeiten:
    deutlich fallen („Verkaufen wäre besser gewesen“), seitwärts, deutlich steigen. „Deutlich“ heißt mehr als eine
    halbe übliche Schwankung über den Horizont (abhängig von der Volatilität des Werts).

Woraus es lernt (Merkmalsgruppen)
    Technik     Renditen über 1–120 Tage, Schwankung, RSI, MACD, Abstand zu den Durchschnitten, Bollinger, Volumen …
    Markt       S&P 500, DAX, VIX, US-Zinsen, Dollar, Öl, Gold, Kupfer, Stärke der eigenen Branche (Branchen-ETFs)
    Makro       Zinsen, Inflation, Zinskurve, Risikoaufschläge, Wirtschaftsstimmung – jeweils nur, was an dem Tag
                schon veröffentlicht war (macro.asof_frame)
    Stimmung    News-Stimmung und Social-Stimmung/Aufmerksamkeit. Diese Reihen gibt es erst ab dem Start der
                Aufzeichnung – das Modell bezieht sie automatisch ein, sobald genug Geschichte da ist.

Wie es sich selbst hinterfragt
    1. Walk-forward-Prüfung: trainiert nur auf der Vergangenheit, testet auf den jeweils folgenden 3 Monaten (mit
       Sicherheitsabstand, damit keine Zukunft durchsickert). Mehrere Varianten (mit/ohne Makro, flach/tief)
       treten gegeneinander an; die beste wird genommen.
    2. Kann das Modell auf ungesehenen Daten nichts besser als der Zufall (Basisrate), bekommt es kein Gewicht –
       dann gelten nur die Regeln.
    3. Entscheidungsjournal: Jeden Abend wird für jeden Wert festgehalten, was Regeln und Modell geraten haben. Nach
       Ablauf des Horizonts wird nachgerechnet: Wäre Verkaufen besser gewesen? Halten? Daraus entstehen Urteile und
       „Lektionen“ (welche Datengruppe hat in die falsche Richtung gezogen). Wer öfter richtig lag – Regeln oder
       Modell –, bekommt mehr Gewicht.
    4. Jede Nacht wird neu trainiert; frisch bewertete Entscheidungen fließen als Trainingsbeispiele mit ein.

Keine Anlageberatung. Märkte sind schwer vorherzusagen – das Modell zeigt deshalb immer, wie sicher es ist und wie
gut es in der Vergangenheit war.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import analysis, macro, market, marketstore
from . import indicators as ind

log = logging.getLogger(__name__)

HORIZON_DAYS = {"short": 5, "medium": 20, "long": 60}
CLASSES = ["down", "flat", "up"]
MIN_ROWS = 4000
FOLD_DAYS = 63
FOLDS = 3

# Grundgesamtheit fürs Lernen (zusätzlich zu allem, was Nutzer beobachten oder halten)
BASE_UNIVERSE = [
    "SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "AIR.DE", "MBG.DE", "BMW.DE", "BAS.DE", "MUV2.DE", "IFX.DE", "DHL.DE",
    "ADS.DE", "DB1.DE", "BAYN.DE", "VOW3.DE", "RWE.DE", "EOAN.DE", "DBK.DE", "CBK.DE", "HEN3.DE", "MRK.DE", "BEI.DE",
    "RHM.DE", "MTX.DE", "CON.DE", "FRE.DE", "ZAL.DE", "VNA.DE", "HEI.DE", "SY1.DE",
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "JNJ", "XOM", "PG", "KO", "WMT", "UNH",
    "HD", "BAC", "AVGO", "COST", "NFLX", "ASML.AS", "MC.PA", "NESN.SW", "NOVO-B.CO",
    "SPY", "QQQ", "EWG", "EEM", "IWDA.AS",
]

TECH = ["ret_1", "ret_5", "ret_20", "ret_60", "ret_120", "vol_20", "vol_60", "atr_pct", "rsi", "macd_hist", "stoch",
        "dist_sma20", "dist_sma50", "dist_sma200", "sma50_slope", "bb_width", "bb_pos", "vol_z", "hi_252", "lo_252",
        "adx", "dd_60", "up_days_10", "gap"]
MARKET = ["spx_ret_20", "spx_dist200", "dax_ret_20", "vix", "vix_chg_5", "tnx_chg_20", "dxy_ret_20", "oil_ret_20",
          "gold_ret_20", "copper_ret_20", "rel_spx_20", "sector_rel_20"]
MACRO_IDS = ["ecb_rate", "ea_inflation", "us_rate", "us_inflation", "us_curve", "us_credit", "ea_sentiment",
             "us_sentiment", "de_unemployment", "us_unemployment"]
MACRO = [f"{i}{s}" for i in MACRO_IDS for s in ("", "_chg")]
SENTIMENT = ["news_sent", "news_sent_5", "social_score", "social_buzz", "attention"]
GROUPS = {"Technik": TECH, "Markt": MARKET, "Makro": MACRO, "Stimmung": SENTIMENT}
GROUP_TEXT = {"Technik": "Kursverlauf und Indikatoren", "Markt": "Marktumfeld (Indizes, VIX, Zinsen, Rohstoffe, Branche)",
              "Makro": "Konjunktur (Zinsen, Inflation, Stimmung, Arbeitsmarkt)", "Stimmung": "News und soziale Netzwerke"}

CONFIGS = {
    "ausgewogen": {"groups": ["Technik", "Markt", "Makro", "Stimmung"],
                   "params": {"max_iter": 300, "learning_rate": 0.03, "max_leaf_nodes": 15, "max_depth": 4,
                              "min_samples_leaf": 200, "l2_regularization": 2.0}},
    "tief": {"groups": ["Technik", "Markt", "Makro", "Stimmung"],
             "params": {"max_iter": 400, "learning_rate": 0.03, "max_leaf_nodes": 31, "max_depth": 6,
                        "min_samples_leaf": 100, "l2_regularization": 1.0}},
    "ohne Makro": {"groups": ["Technik", "Markt", "Stimmung"],
                   "params": {"max_iter": 300, "learning_rate": 0.03, "max_leaf_nodes": 15, "max_depth": 4,
                              "min_samples_leaf": 200, "l2_regularization": 2.0}},
    "nur Kurse": {"groups": ["Technik", "Markt"],
                  "params": {"max_iter": 250, "learning_rate": 0.03, "max_leaf_nodes": 15, "max_depth": 4,
                             "min_samples_leaf": 250, "l2_regularization": 2.0}},
}

_LOCK = threading.Lock()        # schützt nur den Modell-Zwischenspeicher
_TRAIN_LOCK = threading.Lock()  # immer nur ein Training gleichzeitig
_MODELS: dict[str, tuple[float, object, dict]] = {}
STATUS: dict = {"running": False, "step": "", "progress": 0.0, "started": None, "finished": None, "error": None}


# ---------- Merkmale ----------

def tech_features(df: pd.DataFrame) -> pd.DataFrame:
    c, v = df["close"], df["volume"].fillna(0)
    r = np.log(c).diff()
    f = pd.DataFrame(index=df.index)
    for n in (1, 5, 20, 60, 120):
        f[f"ret_{n}"] = np.log(c / c.shift(n))
    f["vol_20"] = r.rolling(20).std()
    f["vol_60"] = r.rolling(60).std()
    f["atr_pct"] = ind.atr(df, 14) / c
    f["rsi"] = ind.rsi(c, 14) / 100
    f["macd_hist"] = ind.macd(c)["hist"] / c
    f["stoch"] = ind.stochastic(df)["stoch_k"] / 100
    for n in (20, 50, 200):
        f[f"dist_sma{n}"] = c / ind.sma(c, n) - 1
    s50 = ind.sma(c, 50)
    f["sma50_slope"] = s50 / s50.shift(10) - 1
    bb = ind.bollinger(c)
    f["bb_width"], f["bb_pos"] = bb["bb_width"], bb["bb_pctb"]
    f["vol_z"] = np.log((v + 1) / (v.rolling(20).mean() + 1))
    f["hi_252"] = c / c.rolling(252, min_periods=60).max() - 1
    f["lo_252"] = c / c.rolling(252, min_periods=60).min() - 1
    f["adx"] = ind.adx(df)["adx"] / 100
    f["dd_60"] = c / c.rolling(60).max() - 1
    f["up_days_10"] = (r > 0).astype(float).rolling(10).mean()
    f["gap"] = np.log(df["open"] / c.shift(1))
    return f.replace([np.inf, -np.inf], np.nan)


def _days_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return idx.normalize()


def _daily_close(symbol: str) -> pd.Series | None:
    store = marketstore.get_store()
    if store is None:
        return None
    df = store.daily(symbol)
    if df.empty:
        return None
    return df["close"]


def market_frame() -> pd.DataFrame:
    """Marktmerkmale je Kalendertag (um einen Tag verschoben: nur was zum Entscheidungszeitpunkt bekannt war)."""
    cols = {}
    raw = {s: _daily_close(s) for s in macro.MODEL_SYMBOLS}

    def ret(s, n):
        return np.log(s / s.shift(n))

    if raw.get("^GSPC") is not None:
        s = raw["^GSPC"]
        cols["spx_ret_20"] = ret(s, 20)
        cols["spx_dist200"] = s / s.rolling(200).mean() - 1
    if raw.get("^GDAXI") is not None:
        cols["dax_ret_20"] = ret(raw["^GDAXI"], 20)
    if raw.get("^VIX") is not None:
        cols["vix"] = raw["^VIX"] / 100
        cols["vix_chg_5"] = np.log(raw["^VIX"] / raw["^VIX"].shift(5))
    if raw.get("^TNX") is not None:
        cols["tnx_chg_20"] = raw["^TNX"] - raw["^TNX"].shift(20)
    for sym, name in (("DX-Y.NYB", "dxy"), ("CL=F", "oil"), ("GC=F", "gold"), ("HG=F", "copper")):
        if raw.get(sym) is not None:
            cols[f"{name}_ret_20"] = ret(raw[sym].where(raw[sym] > 0), 20)
    for etf in macro.SECTOR_ETFS.values():
        if raw.get(etf) is not None:
            cols[f"sec_{etf}"] = ret(raw[etf], 20)
    if not cols:
        return pd.DataFrame()
    frame = pd.DataFrame(cols)
    frame.index = _days_index(frame)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    full = pd.date_range(frame.index.min(), pd.Timestamp(date.today()), freq="D")
    return frame.reindex(full).ffill().shift(1)


def sentiment_frame(symbol: str, days: pd.DatetimeIndex) -> pd.DataFrame:
    store = marketstore.get_store()
    out = pd.DataFrame(index=days, columns=SENTIMENT, dtype=float)
    if store is None:
        return out
    news_hist = store.get(f"news_hist:{symbol.upper()}") or {}
    soc = store.get(f"social_hist:{symbol.upper()}") or {}
    if news_hist:
        s = pd.Series(news_hist, dtype=float)
        s.index = pd.to_datetime(s.index)
        s = s.sort_index()
        out["news_sent"] = s.reindex(s.index.union(days)).ffill(limit=3).reindex(days)
        out["news_sent_5"] = s.rolling(5, min_periods=2).mean().reindex(s.index.union(days)).ffill(limit=3).reindex(days)
    if soc:
        df = pd.DataFrame.from_dict(soc, orient="index")
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        for src, dst, fn in (("score", "social_score", None), ("buzz", "social_buzz", np.log1p),
                             ("attention", "attention", np.log)):
            if src in df:
                col = pd.to_numeric(df[src], errors="coerce")
                if fn is not None:
                    col = fn(col.where(col > 0))
                out[dst] = col.reindex(col.index.union(days)).ffill(limit=3).reindex(days)
    return out


def sector_of(symbol: str) -> str | None:
    """Branchen-ETF eines Werts (zwischengespeichert, 30 Tage)."""
    store = marketstore.get_store()
    key = f"sector:{symbol.upper()}"
    if store is not None:
        hit = store.get(key, max_age=30 * 86400)
        if hit is not None:
            return hit.get("etf")
    etf = None
    try:
        from . import fundamentals

        info = market.cached_info(symbol) or {}
        f = fundamentals.get(symbol, info.get("name"))
        etf = macro.sector_etf(f.get("sector"), f.get("industry"))
    except Exception as exc:  # noqa: BLE001
        log.debug("Branche %s: %s", symbol, exc)
    if store is not None:
        store.put(key, {"etf": etf})
    return etf


def build(symbol: str, df: pd.DataFrame, mkt: pd.DataFrame, mac: pd.DataFrame | None,
          sector: str | None = None) -> pd.DataFrame:
    """Alle Merkmale eines Werts je Handelstag."""
    f = tech_features(df)
    f.index = _days_index(f)
    f = f[~f.index.duplicated(keep="last")]
    days = f.index
    if not mkt.empty:
        m = mkt.reindex(days)
        for col in MARKET:
            if col in m:
                f[col] = m[col]
        if "spx_ret_20" in m:
            f["rel_spx_20"] = f["ret_20"] - m["spx_ret_20"]
        if sector and f"sec_{sector}" in m and "spx_ret_20" in m:
            f["sector_rel_20"] = m[f"sec_{sector}"] - m["spx_ret_20"]
    if mac is not None and not mac.empty:
        mm = mac.reindex(days)
        for col in MACRO:
            if col in mm:
                f[col] = mm[col]
    s = sentiment_frame(symbol, days)
    for col in SENTIMENT:
        f[col] = s[col]
    for col in TECH + MARKET + MACRO + SENTIMENT:
        if col not in f:
            f[col] = np.nan
    f["close"] = _close_on_days(df, days)
    return f


def _close_on_days(df: pd.DataFrame, days: pd.DatetimeIndex) -> pd.Series:
    c = df["close"].copy()
    c.index = _days_index(df)
    c = c[~c.index.duplicated(keep="last")]
    return c.reindex(days)


def labels(close: pd.Series, vol: pd.Series, h: int) -> tuple[pd.Series, pd.Series]:
    """Folgerendite über h Handelstage und Klasse (0 fallen, 1 seitwärts, 2 steigen)."""
    fwd = close.shift(-h) / close - 1
    thr = 0.5 * vol * math.sqrt(h)
    cls = pd.Series(np.where(fwd > thr, 2, np.where(fwd < -thr, 0, 1)), index=close.index, dtype=float)
    cls[fwd.isna() | thr.isna()] = np.nan
    return fwd, cls


# ---------- Datensatz und Training ----------

def universe(storage) -> list[str]:
    syms = set(BASE_UNIVERSE)
    if storage is not None:
        syms.update(s for s in storage.all_tracked_symbols())
    return sorted(s for s in syms if not s.startswith("^") and not s.endswith("=X") and not s.endswith("=F"))


def _history(symbol: str) -> pd.DataFrame | None:
    try:
        return market.get_history(symbol, "5y", "1d")
    except Exception as exc:  # noqa: BLE001
        log.info("Keine Historie für %s: %s", symbol, exc)
        return None


def dataset(symbols: list[str], horizon: str, progress=None, frames: dict | None = None) -> pd.DataFrame:
    """Lange Tabelle: eine Zeile je (Wert, Tag) mit Merkmalen, Folgerendite und Klasse."""
    h = HORIZON_DAYS[horizon]
    mkt = market_frame()
    parts = []
    mac_cache: pd.DataFrame | None = None
    for i, sym in enumerate(symbols):
        df = (frames or {}).get(sym)
        if df is None:
            df = _history(sym)
        if df is None or len(df) < 260:
            continue
        f = build(sym, df, mkt, None, sector_of(sym) if frames is None else None)
        if mac_cache is None:
            mac_cache = macro.asof_frame(pd.date_range("2010-01-01", pd.Timestamp(date.today()), freq="D"), MACRO_IDS)
        if not mac_cache.empty:
            mm = mac_cache.reindex(f.index)
            for col in MACRO:
                if col in mm:
                    f[col] = mm[col]
        fwd, cls = labels(f["close"], f["vol_20"], h)
        f["fwd"], f["y"], f["symbol"] = fwd, cls, sym
        parts.append(f.iloc[200:])  # Vorlauf für die 200-Tage-Linie
        if progress:
            progress(i + 1, len(symbols))
    if not parts:
        return pd.DataFrame()
    data = pd.concat(parts)
    data.index.name = "day"
    return data


def _features_for(groups: list[str], data: pd.DataFrame | None = None, min_count: int = 200) -> list[str]:
    """Merkmale der Gruppen – nur solche, für die es genug Werte gibt (z. B. Stimmung erst nach einigen Monaten
    Aufzeichnung). Leere Spalten würden das Training nur stören."""
    cols = [c for g in groups for c in GROUPS[g]]
    if data is None:
        return cols
    return [c for c in cols if c in data and int(data[c].notna().sum()) >= min_count]


def _weights(days: pd.DatetimeIndex, ref: pd.Timestamp) -> np.ndarray:
    age = (ref - days).days.to_numpy(dtype=float)
    return np.power(0.5, np.clip(age, 0, None) / 730.0)


class Shrunk:
    """Gradient-Boosting-Modell, dessen Wahrscheinlichkeiten zur Basisrate hin gezogen werden – so stark, wie es die
    zeitlich letzte Validierung verlangt. Ein Modell ohne nachweisbares Können landet so bei der Basisrate statt
    falsche Gewissheit zu verbreiten („Selbstzweifel“ eingebaut)."""

    def __init__(self, model, alpha: float, prior: np.ndarray, n_iter: int, val_gain: float):
        self.model, self.alpha, self.prior, self.n_iter, self.val_gain = model, alpha, prior, n_iter, val_gain

    def raw_proba(self, X: pd.DataFrame) -> np.ndarray:
        p = self.model.predict_proba(X)
        out = np.zeros((len(X), 3))
        for j, c in enumerate(self.model.classes_):
            out[:, int(c)] = p[:, j]
        return out

    def proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.alpha * self.raw_proba(X) + (1 - self.alpha) * self.prior


def _hgb(params: dict, n_iter: int | None = None):
    from sklearn.ensemble import HistGradientBoostingClassifier

    p = dict(params)
    if n_iter is not None:
        p["max_iter"] = n_iter
    return HistGradientBoostingClassifier(random_state=7, early_stopping=False, **p)


def _fit(X: pd.DataFrame, y: np.ndarray, w: np.ndarray, params: dict, days: pd.DatetimeIndex | None = None,
         h: int = 20) -> Shrunk:
    """Mit zeitlicher Validierung (letzte 15 % der Tage, mit Sicherheitsabstand): beste Zahl an Bäumen und
    Schrumpfung bestimmen, dann auf allen Daten neu trainieren."""
    prior = np.bincount(y, minlength=3) / len(y)
    n_iter, alpha, gain = params.get("max_iter", 200), 1.0, 0.0
    if days is not None:
        uniq = np.array(sorted(pd.DatetimeIndex(days).unique()))
        if len(uniq) > 300:
            v_start = uniq[int(len(uniq) * 0.85)]
            fit_end = uniq[max(0, int(len(uniq) * 0.85) - h - 1)]
            di = pd.DatetimeIndex(days)
            fit_m, val_m = np.asarray(di < fit_end), np.asarray(di >= v_start)
            if fit_m.sum() > 1000 and val_m.sum() > 200:
                m = _hgb(params).fit(X[fit_m], y[fit_m], sample_weight=w[fit_m])
                yv = y[val_m]
                pv_prior = np.bincount(y[fit_m], minlength=3) / fit_m.sum()
                best = (np.inf, n_iter, None)
                for i, pv in enumerate(m.staged_predict_proba(X[val_m]), start=1):
                    full = np.zeros((len(yv), 3))
                    for j, c in enumerate(m.classes_):
                        full[:, int(c)] = pv[:, j]
                    ll = _logloss(full, yv)
                    if ll < best[0]:
                        best = (ll, i, full)
                n_iter, pr = max(10, best[1]), best[2]
                base_ll = _logloss(np.tile(pv_prior, (len(yv), 1)), yv)
                scores = [(_logloss(a * pr + (1 - a) * pv_prior, yv), a) for a in np.linspace(0, 1, 11)]
                ll_best, alpha = min(scores)
                gain = base_ll - ll_best
    model = _hgb(params, n_iter).fit(X, y, sample_weight=w)
    return Shrunk(model, float(alpha), prior, int(n_iter), float(gain))


def _proba(model, X: pd.DataFrame) -> np.ndarray:
    if isinstance(model, Shrunk):
        return model.proba(X)
    p = model.predict_proba(X)
    out = np.zeros((len(X), 3))
    for j, c in enumerate(model.classes_):
        out[:, int(c)] = p[:, j]
    return out


def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    eps = 1e-9
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y.astype(int)], eps, 1))))


def evaluate(p: np.ndarray, y: np.ndarray, fwd: np.ndarray, prior: np.ndarray) -> dict:
    """Güte auf ungesehenen Daten – auch in der Sprache der Entscheidung (Halten vs. Verkaufen)."""
    ll, ll0 = _logloss(p, y), _logloss(np.tile(prior, (len(y), 1)), y)
    exp = p[:, 2] - p[:, 0]
    sell, buy = exp < -0.15, exp > 0.15
    base = float(np.mean(fwd)) if len(fwd) else 0.0
    return {
        "n": int(len(y)), "logloss": round(ll, 4), "logloss_base": round(ll0, 4), "gain": round(ll0 - ll, 4),
        "accuracy": round(float(np.mean(np.argmax(p, 1) == y)), 3),
        "accuracy_base": round(float(np.mean(y == np.argmax(prior))), 3),
        "avg_return": round(base * 100, 2),
        "sell_signals": int(sell.sum()),
        # Wie oft fiel der Kurs wirklich, wenn das Modell „Verkaufen wäre besser“ sah – und wie viel wurde vermieden
        "sell_hit": round(float(np.mean(y[sell] == 0)), 3) if sell.any() else None,
        "sell_avoided": round(float(np.mean(fwd[sell]) * -100), 2) if sell.any() else None,
        "buy_signals": int(buy.sum()),
        "buy_hit": round(float(np.mean(y[buy] == 2)), 3) if buy.any() else None,
        "buy_return": round(float(np.mean(fwd[buy]) * 100), 2) if buy.any() else None,
        # Rendite, wenn man der Richtung des Modells folgt, minus „immer halten“
        "edge": round(float(np.mean(np.sign(exp) * fwd) - base) * 100, 3) if len(fwd) else 0.0,
    }


def walk_forward(data: pd.DataFrame, horizon: str, config: dict, folds: int = FOLDS) -> list[dict]:
    h = HORIZON_DAYS[horizon]
    lab = data[data["y"].notna()]
    days = np.array(sorted(lab.index.unique()))
    if len(days) < FOLD_DAYS * (folds + 2):
        return []
    out = []
    for k in range(folds):
        end_i = len(days) - 1 - k * FOLD_DAYS
        start_i = end_i - FOLD_DAYS + 1
        test_days = days[start_i:end_i + 1]
        cutoff = days[max(0, start_i - h - 1)]  # Sicherheitsabstand: Labels des Trainings enden vor dem Test
        tr = lab[lab.index < cutoff]
        te = lab[(lab.index >= test_days[0]) & (lab.index <= test_days[-1])]
        if len(tr) < MIN_ROWS or len(te) < 200:
            continue
        feats = _features_for(config["groups"], tr)
        y_tr = tr["y"].to_numpy().astype(int)
        prior = np.bincount(y_tr, minlength=3) / len(y_tr)
        model = _fit(tr[feats], y_tr, _weights(pd.DatetimeIndex(tr.index), pd.Timestamp(cutoff)), config["params"],
                     days=pd.DatetimeIndex(tr.index), h=h)
        p = _proba(model, te[feats])
        m = evaluate(p, te["y"].to_numpy().astype(int), te["fwd"].to_numpy(), prior)
        m.update(test_from=str(pd.Timestamp(test_days[0]).date()), test_to=str(pd.Timestamp(test_days[-1]).date()))
        if k == 0:
            m["groups"] = group_importance(model, te[feats], te["y"].to_numpy().astype(int), config["groups"])
        out.append(m)
    return out


def group_importance(model, X: pd.DataFrame, y: np.ndarray, groups: list[str], seed: int = 3) -> dict:
    """Wie viel schlechter wird die Vorhersage, wenn eine Datengruppe zufällig vertauscht wird? (in Promille)"""
    rng = np.random.default_rng(seed)
    base = _logloss(_proba(model, X), y)
    out = {}
    for g in groups:
        cols = [c for c in GROUPS[g] if c in X]
        if not cols or X[cols].isna().all().all():
            out[g] = 0.0
            continue
        Xp = X.copy()
        perm = rng.permutation(len(X))
        Xp[cols] = X[cols].to_numpy()[perm]
        out[g] = round((_logloss(_proba(model, Xp), y) - base) * 1000, 2)
    return out


def _summary(folds: list[dict]) -> dict:
    if not folds:
        return {"gain": None, "edge": None}
    return {"gain": round(float(np.mean([f["gain"] for f in folds])), 4),
            "edge": round(float(np.mean([f["edge"] for f in folds])), 3),
            "accuracy": round(float(np.mean([f["accuracy"] for f in folds])), 3),
            "accuracy_base": round(float(np.mean([f["accuracy_base"] for f in folds])), 3)}


def skill_of(summary: dict) -> float:
    """0 = nicht besser als die Basisrate, 1 = deutlich besser (Logloss-Gewinn ≥ 0,02 und positive Kante)."""
    g, e = summary.get("gain"), summary.get("edge")
    if g is None or g <= 0 or (e is not None and e < 0):
        return 0.0
    return round(min(1.0, g / 0.02), 3)


def model_dir() -> Path:
    from .config import settings

    d = settings.data_dir / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _set_status(**kw) -> None:
    STATUS.update(kw)


def train(storage, horizon: str, symbols: list[str] | None = None, frames: dict | None = None) -> dict:
    """Varianten per Walk-forward vergleichen, die beste auf allen Daten trainieren und speichern."""
    import joblib

    symbols = symbols or universe(storage)
    _set_status(step=f"{horizon}: Daten sammeln", progress=0.0)
    data = dataset(symbols, horizon, progress=lambda i, n: _set_status(progress=round(0.4 * i / n, 3)), frames=frames)
    if not data.empty:  # halber Arbeitsspeicher: Merkmale als float32 (das Modell rechnet ohnehin mit Klassen-Bins)
        num = [c for c in data.columns if c not in ("y", "symbol", "fwd") and pd.api.types.is_float_dtype(data[c])]
        data[num] = data[num].astype("float32")
    lab = data[data["y"].notna()] if not data.empty else data
    if len(lab) < MIN_ROWS:
        raise RuntimeError(f"Zu wenig Daten zum Lernen ({len(lab)} Zeilen, nötig {MIN_ROWS}).")
    candidates = {}
    for i, (name, cfg) in enumerate(CONFIGS.items()):
        _set_status(step=f"{horizon}: Variante „{name}“ prüfen", progress=round(0.4 + 0.45 * i / len(CONFIGS), 3))
        folds = walk_forward(data, horizon, cfg)
        candidates[name] = {"folds": folds, **_summary(folds)}
    best = max(candidates, key=lambda n: (candidates[n]["gain"] if candidates[n]["gain"] is not None else -9,
                                          candidates[n]["edge"] or 0))
    cfg = CONFIGS[best]
    feats = _features_for(cfg["groups"], lab)
    _set_status(step=f"{horizon}: Variante „{best}“ auf allen Daten trainieren", progress=0.9)
    y = lab["y"].to_numpy().astype(int)
    ref = pd.Timestamp(lab.index.max())
    w = _weights(pd.DatetimeIndex(lab.index), ref)
    w = w * _journal_boost(storage, lab, horizon)
    model = _fit(lab[feats], y, w, cfg["params"], days=pd.DatetimeIndex(lab.index), h=HORIZON_DAYS[horizon])
    medians = {c: (float(lab[c].median()) if lab[c].notna().any() else None) for c in feats}
    summary = candidates[best]
    version = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    meta = {
        "version": version, "horizon": horizon, "days": HORIZON_DAYS[horizon], "config": best, "features": feats,
        "groups": cfg["groups"], "medians": medians, "rows": int(len(lab)), "symbols": int(lab["symbol"].nunique()),
        "from": str(pd.Timestamp(lab.index.min()).date()), "to": str(ref.date()),
        "prior": (np.bincount(y, minlength=3) / len(y)).round(4).tolist(),
        "candidates": {k: {kk: vv for kk, vv in v.items() if kk != "folds"} for k, v in candidates.items()},
        "folds": summary["folds"], "summary": {k: v for k, v in summary.items() if k != "folds"},
        "skill": skill_of(summary), "trained_at": time.time(),
        "feature_coverage": {g: round(float(lab[GROUPS[g]].notna().any(axis=1).mean()), 3) for g in cfg["groups"]},
    }
    path = model_dir() / f"brain-{horizon}.joblib"
    if path.exists():
        path.replace(model_dir() / f"brain-{horizon}.prev.joblib")
    joblib.dump(model, path)
    store = marketstore.get_store()
    if store is not None:
        hist = store.get(f"brain:history:{horizon}") or []
        hist.append({"version": version, "config": best, "skill": meta["skill"], **meta["summary"]})
        store.put(f"brain:history:{horizon}", hist[-60:])
        store.put(f"brain:meta:{horizon}", meta)
    with _LOCK:
        _MODELS[horizon] = (time.time(), model, meta)
    return meta


def _journal_boost(storage, lab: pd.DataFrame, horizon: str) -> np.ndarray:
    """Tage, an denen das System eine echte Entscheidung getroffen hat und danebenlag, zählen beim Lernen doppelt –
    genau aus diesen Fehlern soll es lernen."""
    boost = np.ones(len(lab))
    if storage is None:
        return boost
    wrong = {(d["symbol"], d["day"]) for d in storage.decisions(evaluated=True, limit=20000, horizon=horizon)
             if (d.get("verdict") or "").startswith(("Verkaufen wäre", "Halten wäre", "Kauf war"))}
    if not wrong:
        return boost
    keys = list(zip(lab["symbol"], [str(pd.Timestamp(d).date()) for d in lab.index], strict=True))
    for i, k in enumerate(keys):
        if k in wrong:
            boost[i] = 2.0
    return boost


def load(horizon: str):
    """(Modell, Metadaten) oder (None, None)."""
    with _LOCK:
        hit = _MODELS.get(horizon)
    if hit:
        return hit[1], hit[2]
    path = model_dir() / f"brain-{horizon}.joblib"
    store = marketstore.get_store()
    meta = store.get(f"brain:meta:{horizon}") if store else None
    if not path.exists() or not meta:
        return None, None
    try:
        import joblib

        model = joblib.load(path)
    except Exception as exc:  # noqa: BLE001
        log.warning("Modell %s nicht ladbar: %s", horizon, exc)
        return None, None
    with _LOCK:
        _MODELS[horizon] = (time.time(), model, meta)
    return model, meta


# ---------- Vorhersage und Erklärung ----------

def _row_for(symbol: str, df: pd.DataFrame | None = None) -> pd.DataFrame | None:
    df = df if df is not None else _history(symbol)
    if df is None or len(df) < 220:
        return None
    mkt = market_frame()
    f = build(symbol, df, mkt, None, sector_of(symbol))
    last = f.iloc[[-1]].copy()
    mac = macro.asof_frame(pd.date_range(pd.Timestamp(date.today()) - pd.Timedelta(days=200),
                                         pd.Timestamp(date.today()), freq="D"), MACRO_IDS)
    if not mac.empty:
        for col in MACRO:
            if col in mac:
                last[col] = mac[col].iloc[-1]
    return last


def explain(model, meta: dict, row: pd.DataFrame) -> list[dict]:
    """Welche Datengruppe zieht die Einschätzung wohin? Gruppe auf den typischen Wert setzen und vergleichen."""
    feats = meta["features"]
    p = _proba(model, row[feats])[0]
    full = p[2] - p[0]
    out = []
    for g in meta["groups"]:
        cols = [c for c in GROUPS[g] if c in feats]
        if not cols:
            continue
        r2 = row[feats].copy()
        for c in cols:
            r2[c] = meta["medians"].get(c)
        q = _proba(model, r2.astype(float))[0]
        delta = full - (q[2] - q[0])
        if all(pd.isna(row[c].iloc[0]) for c in cols):
            continue
        out.append({"group": g, "text": GROUP_TEXT[g], "delta": round(float(delta), 3)})
    out.sort(key=lambda d: -abs(d["delta"]))
    return out


def predict(symbol: str, horizon: str, df: pd.DataFrame | None = None) -> dict | None:
    model, meta = load(horizon)
    if model is None:
        return None
    row = _row_for(symbol, df)
    if row is None:
        return None
    p = _proba(model, row[meta["features"]].astype(float))[0]
    expected = float(p[2] - p[0])
    action = analysis.BUY if expected > 0.15 and p[2] > 0.4 else analysis.SELL if expected < -0.15 and p[0] > 0.4 \
        else analysis.HOLD
    conf = float(max(p))
    return {"symbol": symbol.upper(), "horizon": horizon, "days": meta["days"], "p_down": round(float(p[0]), 3),
            "p_flat": round(float(p[1]), 3), "p_up": round(float(p[2]), 3), "expected": round(expected, 3),
            "confidence": round(conf, 3), "action": action, "version": meta["version"], "skill": meta["skill"],
            "drivers": explain(model, meta, row), "day": date.today().isoformat(),
            "features": {k: (None if pd.isna(v) else round(float(v), 5)) for k, v in row.iloc[0].items()
                         if k in ("ret_20", "rsi", "dist_sma200", "vol_20", "vix", "news_sent", "social_score",
                                  "attention", "spx_ret_20", "rel_spx_20")}}


def weight(horizon: str, settings=None) -> float:
    """Wie stark das Modell neben den Regeln zählt: Können auf ungesehenen Daten × Bilanz im Journal."""
    from .config import settings as base

    cfg = settings or base
    if not getattr(cfg, "model_enabled", True):
        return 0.0
    _, meta = load(horizon)
    if not meta:
        return 0.0
    track = track_record(horizon)
    factor = 1.0
    if track["n"] >= 30 and track["model_acc"] is not None and track["rule_acc"] is not None:
        factor = min(1.5, max(0.3, 1 + 2 * (track["model_acc"] - track["rule_acc"])))
    return round(min(float(cfg.model_weight_max), float(cfg.model_weight_max) * meta["skill"] * factor), 3)


def combine(rule_score: float, rule_action: str, pred: dict | None, w: float, profile: analysis.Profile) -> dict:
    """Regeln und Modell zu einer Einschätzung zusammenführen (gleiche Schwellen wie beim Risikoprofil)."""
    if not pred or w <= 0:
        return {"action": rule_action, "score": rule_score, "weight": 0.0}
    score = round((1 - w) * rule_score + w * pred["expected"], 3)
    R = profile.r
    action = analysis.BUY if score >= R["buy"] else analysis.SELL if score <= R["sell"] else analysis.HOLD
    # Ein Kauf braucht weiterhin die Zustimmung der Regeln (Trendfilter, Chance/Risiko) – das Modell darf nur
    # bremsen oder zum Verkauf raten, nicht allein einen Kauf auslösen.
    if action == analysis.BUY and rule_action != analysis.BUY:
        action = analysis.HOLD
    return {"action": action, "score": score, "weight": w}


# ---------- Entscheidungsjournal: festhalten, nachrechnen, lernen ----------

def _verdict(final: str, cls: int, fwd: float, days: int) -> tuple[str, bool]:
    pct = f"{fwd * 100:+.1f} %".replace(".", ",")
    if final == analysis.SELL:
        if cls == 0:
            return f"Richtig: Verkaufen hat {pct} in {days} Tagen erspart", True
        if cls == 2:
            return f"Halten wäre besser gewesen ({pct} in {days} Tagen)", False
        return f"Vertretbar: kaum Bewegung ({pct})", True
    if final == analysis.BUY:
        if cls == 2:
            return f"Richtig: Kauf brachte {pct} in {days} Tagen", True
        if cls == 0:
            return f"Kauf war verfrüht – Verkaufen wäre besser gewesen ({pct})", False
        return f"Kaum Bewegung nach dem Kaufsignal ({pct})", True
    if cls == 0:
        return f"Verkaufen wäre besser gewesen ({pct} in {days} Tagen)", False
    return (f"Richtig gehalten ({pct})" if cls == 2 else f"Richtig: seitwärts ({pct})"), True


def _correct(action: str | None, cls: int) -> bool | None:
    if not action:
        return None
    if action == analysis.BUY:
        return cls == 2
    if action == analysis.SELL:
        return cls == 0
    return cls != 0


def _lesson(d: dict, cls: int, ok: bool) -> str:
    if ok:
        return ""
    feats = d.get("features") or {}
    drivers = feats.get("drivers") or []
    rule_ok = _correct(d.get("rule_action"), cls)
    model_ok = _correct(d.get("model_action"), cls)
    parts = []
    if rule_ok and not model_ok:
        parts.append("Die Regeln lagen richtig, das Modell nicht – das Modell verliert etwas Gewicht.")
    elif model_ok and not rule_ok:
        parts.append("Das Modell lag richtig, die Regeln nicht – das Modell bekommt mehr Gewicht.")
    want = -1 if cls == 0 else 1
    wrong_way = [x for x in drivers if x["delta"] * want < -0.03]
    if wrong_way:
        g = wrong_way[0]
        parts.append(f"In die falsche Richtung zog vor allem: {g['text']}.")
    if cls == 0 and feats.get("news_sent") is not None and feats["news_sent"] < -0.15:
        parts.append("Die Nachrichtenlage war schon negativ – ein Warnzeichen, das stärker zählen sollte.")
    return " ".join(parts) or "Die Bewegung war aus den Daten nicht absehbar."


def _trading_days_later(day: str, n: int) -> str:
    return (pd.Timestamp(day) + pd.offsets.BDay(n)).strftime("%Y-%m-%d")


def evaluate_journal(storage) -> int:
    """Offene Entscheidungen nachrechnen, deren Horizont abgelaufen ist."""
    n = 0
    today = pd.Timestamp(date.today())
    for d in storage.open_decisions(before_day=(today - pd.offsets.BDay(5)).strftime("%Y-%m-%d")):
        h = HORIZON_DAYS.get(d["horizon"], 20)
        due = _trading_days_later(d["day"], h)
        if pd.Timestamp(due) > today:
            continue
        df = _history(d["symbol"])
        if df is None:
            continue
        c = _close_on_days(df, _days_index(df)).dropna()
        after = c[c.index > pd.Timestamp(d["day"])]
        if len(after) < h:
            continue
        before = c[c.index <= pd.Timestamp(d["day"])]
        start = float(before.iloc[-1]) if len(before) else float(d["price"])
        end = float(after.iloc[h - 1])
        fwd = end / start - 1
        r = np.log(c).diff()
        vol = float(r[c.index <= pd.Timestamp(d["day"])].tail(20).std() or 0.02)
        thr = 0.5 * vol * math.sqrt(h)
        cls = 2 if fwd > thr else 0 if fwd < -thr else 1
        verdict, ok = _verdict(d["final_action"] or d["rule_action"] or analysis.HOLD, cls, fwd, h)
        storage.evaluate_decision(d["id"], round(fwd, 5), CLASSES[cls], verdict, _lesson(d, cls, ok))
        n += 1
    return n


def track_record(horizon: str | None = None, days: int = 180, storage=None) -> dict:
    """Trefferquote von Regeln, Modell und kombinierter Einschätzung im Journal."""
    if storage is None:
        from .deps import get_storage

        storage = get_storage()
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = [d for d in storage.decisions(evaluated=True, limit=20000, horizon=horizon) if d["day"] >= since]
    res = {"n": len(rows), "rule_acc": None, "model_acc": None, "final_acc": None, "sell_better": 0, "hold_better": 0}
    if not rows:
        return res
    for key, name in (("rule_action", "rule_acc"), ("model_action", "model_acc"), ("final_action", "final_acc")):
        vals = [_correct(d.get(key), CLASSES.index(d["outcome_label"])) for d in rows if d.get(key)]
        vals = [v for v in vals if v is not None]
        res[name] = round(sum(vals) / len(vals), 3) if vals else None
    res["sell_better"] = sum(1 for d in rows if (d.get("verdict") or "").startswith(("Verkaufen wäre", "Kauf war")))
    res["hold_better"] = sum(1 for d in rows if (d.get("verdict") or "").startswith("Halten wäre"))
    return res


def record_sentiment(symbol: str, score: float | None) -> None:
    if score is None:
        return
    store = marketstore.get_store()
    if store is None:
        return
    key = f"news_hist:{symbol.upper()}"
    hist = store.get(key) or {}
    hist[date.today().isoformat()] = round(float(score), 3)
    if len(hist) > 900:
        for k in sorted(hist)[:-900]:
            hist.pop(k, None)
    store.put(key, hist)


def horizons_in_use(storage, base) -> list[str]:
    from . import settings_store

    hs = {"medium"}
    for u in storage.users():
        hs.add(settings_store.for_user(storage.for_user(u["id"]), base).invest_horizon)
    return [h for h in HORIZON_DAYS if h in hs]


def daily(storage, base) -> dict:
    """Abendlauf: Stimmung festhalten, Vorhersagen rechnen, Entscheidungen ins Journal, alte bewerten."""
    from . import news, settings_store, snapshot

    store = marketstore.get_store()
    evaluated = evaluate_journal(storage)
    symbols = [s for s in storage.all_tracked_symbols()]
    cfg = settings_store.for_user(storage, base)
    made = 0
    for sym in symbols:
        try:
            items = news.collect(sym, cfg, (market.cached_info(sym) or {}).get("name"))
            record_sentiment(sym, news.aggregate_sentiment(items))
        except Exception:  # noqa: BLE001
            pass
    for horizon in horizons_in_use(storage, base):
        w = weight(horizon, base)
        profile = analysis.Profile(horizon, "balanced")
        for sym in symbols:
            try:
                df, a, rec = snapshot.technical(sym, profile, None)
                pred = predict(sym, horizon)
            except Exception as exc:  # noqa: BLE001
                log.info("Vorhersage %s (%s): %s", sym, horizon, exc)
                continue
            if store is not None and pred:
                store.put(f"pred:{horizon}:{sym}", pred)
            comb = combine(rec.combined, rec.action, pred, w, profile)
            feats = dict((pred or {}).get("features") or {})
            feats["drivers"] = (pred or {}).get("drivers") or []
            storage.save_decision({
                "symbol": sym, "day": date.today().isoformat(), "horizon": horizon, "price": a.last_close,
                "rule_action": rec.action, "rule_score": rec.combined,
                "model_action": pred["action"] if pred else None, "p_up": pred["p_up"] if pred else None,
                "p_down": pred["p_down"] if pred else None, "expected": pred["expected"] if pred else None,
                "final_action": comb["action"], "model_version": pred["version"] if pred else None,
                "features": feats})
            made += 1
    return {"evaluated": evaluated, "decisions": made}


def cached_predictions(symbols: list[str], horizon: str) -> dict[str, dict]:
    """Letzte Vorhersagen (vom Abendlauf oder einer Einzelabfrage) plus Gewicht – ohne Rechnen."""
    store = marketstore.get_store()
    if store is None:
        return {}
    w = weight(horizon)
    out = {}
    for s in symbols:
        p = store.get(f"pred:{horizon}:{s.upper()}", max_age=4 * 86400)
        if p:
            out[s.upper()] = {k: p[k] for k in ("p_up", "p_down", "p_flat", "expected", "action", "confidence", "day",
                                               "days") if k in p} | {"weight": w, "drivers": p.get("drivers", [])[:2]}
    return out


# ---------- Hintergrund-Training ----------

def run_training(storage, base, horizons: list[str] | None = None) -> dict:
    if not _TRAIN_LOCK.acquire(blocking=False):
        return {"running": True}
    try:
        _set_status(running=True, started=time.time(), finished=None, error=None, step="Start", progress=0.0)
        store = marketstore.get_store()
        if store is not None:  # Marke für „Lauf wurde abgebrochen“ (Neustart, zu wenig Arbeitsspeicher)
            store.put("brain:last_run", {"started": time.time(), "finished": None, "error": None})
        results = {}
        syms = universe(storage)
        market.ensure_fresh(list(macro.MODEL_SYMBOLS) + syms, quotes=False)
        for h in horizons or horizons_in_use(storage, base):
            try:
                results[h] = {k: v for k, v in train(storage, h, syms).items() if k in ("version", "skill", "summary")}
            except Exception as exc:  # noqa: BLE001
                log.exception("Training %s fehlgeschlagen", h)
                results[h] = {"error": str(exc)}
        failed = {h: r["error"] for h, r in results.items() if isinstance(r, dict) and r.get("error")}
        _set_status(step="Vorhersagen und Journal", progress=0.97)
        results["daily"] = daily(storage, base)
        err = "; ".join(f"{HORIZON_LABEL.get(h, h)}: {e}" for h, e in failed.items()) or None
        _set_status(running=False, finished=time.time(), step="fertig" if not err else "fertig mit Fehlern",
                    progress=1.0, error=err)
        _remember_run(results, err)
        if failed and len(failed) == len([h for h in results if h != "daily"]):
            raise RuntimeError(err)  # nichts gelernt: als Fehler melden, nicht als „ok“
        return results
    except Exception as exc:  # noqa: BLE001
        msg = f"{type(exc).__name__}: {exc}"
        _set_status(running=False, finished=time.time(), error=msg)
        _remember_run({}, msg)
        raise
    finally:
        _TRAIN_LOCK.release()


HORIZON_LABEL = {"short": "kurzfristig", "medium": "mittelfristig", "long": "langfristig"}


def _remember_run(results: dict, err: str | None) -> None:
    """Letzten Lauf dauerhaft merken – STATUS lebt nur im Speicher und ist nach einem Neustart weg."""
    store = marketstore.get_store()
    if store is not None:
        prev = store.get("brain:last_run") or {}
        store.put("brain:last_run", {"started": prev.get("started"), "finished": time.time(), "error": err,
                                     "results": {h: r for h, r in results.items() if h != "daily"}})


def start_training(storage, base) -> bool:
    if STATUS.get("running"):
        return False
    threading.Thread(target=lambda: _safe(storage, base), daemon=True, name="brain").start()
    return True


def _safe(storage, base) -> None:
    try:
        run_training(storage, base)
    except Exception:  # noqa: BLE001
        log.exception("Modelltraining fehlgeschlagen")


def overview(storage) -> dict:
    """Alles für die Modell-Seite."""
    store = marketstore.get_store()
    out = {"status": dict(STATUS), "horizons": {}}
    last = store.get("brain:last_run") if store else None
    if last and not out["status"].get("running") and not out["status"].get("finished"):
        if last.get("started") and not last.get("finished"):
            when = datetime.fromtimestamp(last["started"]).strftime("%d.%m. %H:%M")
            out["status"].update(error=f"Der Lauf vom {when} Uhr wurde abgebrochen, bevor er fertig war – meist ist dem "
                                       "Server der Arbeitsspeicher ausgegangen oder er wurde neu gestartet.")
        else:
            out["status"].update(finished=last.get("finished"), error=last.get("error"))
    for h in HORIZON_DAYS:
        _, meta = load(h)
        if not meta:
            continue
        out["horizons"][h] = {
            **{k: meta.get(k) for k in ("version", "config", "rows", "symbols", "from", "to", "skill", "summary",
                                        "candidates", "folds", "feature_coverage", "days", "prior")},
            "weight": weight(h), "track": track_record(h, storage=storage),
            "history": (store.get(f"brain:history:{h}") if store else None) or [],
        }
    out["journal"] = storage.decisions(evaluated=True, limit=60)
    out["open"] = storage.decisions(evaluated=False, limit=30)
    for d in out["journal"] + out["open"]:
        d.pop("features", None)
        d["name"] = (market.cached_info(d["symbol"]) or {}).get("name")
    return out


def to_json(obj) -> str:
    return json.dumps(obj, default=lambda o: o.item() if hasattr(o, "item") else str(o))
