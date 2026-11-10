"""Schattendepot: ein virtuelles Depot, das die eigenen Empfehlungen automatisch handelt.

Live: Einmal pro Handelstag (Einstellung paper_time) werden alle Werte der Watchlist bewertet.
  - Kaufen, wenn die Einschätzung „Kaufen prüfen“ ist. Stückzahl nach dem Risikoprofil: Ein Stopp kostet
    höchstens das Depotrisiko pro Position, die Position ist höchstens so groß wie die Höchstgewichtung.
  - Verkaufen, wenn der Stopp unterschritten oder das Kursziel erreicht wurde (geprüft an den Tageskerzen seit
    dem letzten Lauf) oder die Einschätzung auf „Reduzieren prüfen“ kippt.
  - Der Stopp wird mit dem Kurs nachgezogen (Schlusskurs minus Stopp-Abstand des Horizonts), nie gesenkt.
  - Pro Order fällt eine feste Gebühr an. Am selben Tag, an dem verkauft wurde, wird derselbe Wert nicht neu gekauft.

Rückblick: Dieselben Regeln laufen über die letzten zwei Jahre, für alle neun Kombinationen aus Horizont und
Risiko. Das erste Jahr ist die Lernphase (welche Variante war am besten?), das zweite die Prüfphase (hält sich
die Variante auch auf Daten, nach denen nicht ausgewählt wurde?). Im Rückblick wird zur Eröffnung des Folgetags
gehandelt, damit keine Kurse verwendet werden, die zum Zeitpunkt der Entscheidung noch unbekannt waren.
Historische Nachrichten gibt es nicht, der Rückblick bewertet daher nur die Technik.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from . import analysis
from . import indicators as ind
from . import market, news, notify

log = logging.getLogger(__name__)

BERLIN = ZoneInfo("Europe/Berlin")
MIN_ORDER = 50.0
WARMUP = 210  # Kerzen Vorlauf, damit die 200-Tage-Linie steht
HORIZONS = ["short", "medium", "long"]
RISKS = ["conservative", "balanced", "aggressive"]
BUY, SELL = analysis.BUY, analysis.SELL


def today() -> str:
    return datetime.now(BERLIN).date().isoformat()


def day_of(ts) -> str:
    """Handelstag einer Kerze. gettex-Tageskerzen beginnen um 23:00 UTC des Vortags (Mitternacht Berlin)."""
    t = pd.Timestamp(ts)
    if t.tzinfo is not None:
        t = t.tz_convert(BERLIN)
    return t.date().isoformat()


@dataclass
class Sig:
    action: str
    close: float
    stop: float | None
    target: float | None
    atr: float | None
    score: float
    reason: str


def to_sig(a: analysis.Analysis, rec: analysis.Recommendation) -> Sig:
    reason = rec.reasons[0] if rec.reasons else ""
    return Sig(rec.action, a.last_close, rec.stop, rec.target, a.metrics.get("atr"), rec.combined, reason)


def _r(x: float | None, n: int = 4) -> float | None:
    return None if x is None else round(float(x), n)


class Book:
    """Kasse, offene Positionen und Orderbuch. Gleiche Regeln für Live und Rückblick."""

    def __init__(self, capital: float, fee: float):
        self.capital = float(capital)
        self.cash = float(capital)
        self.fee = float(fee)
        self.pos: dict[str, dict] = {}
        self.trades: list[dict] = []
        self.sold_on: dict[str, str] = {}

    def value(self, prices: dict[str, float]) -> float:
        return self.cash + sum(p["shares"] * prices.get(s, p["entry"]) for s, p in self.pos.items())

    def size(self, price: float, stop: float | None, profile: analysis.Profile, equity: float) -> float:
        if not price or price <= 0 or stop is None or price - stop <= 0:
            return 0
        R = profile.r
        by_risk = equity * R["risk_per_trade"] / 100 / (price - stop) * price
        budget = min(by_risk, equity * R["max_position"] / 100, self.cash - self.fee)
        if budget < MIN_ORDER:
            return 0
        shares = math.floor(budget / price)
        if shares < 1:  # teurer als die erlaubte Position (z. B. Bitcoin): Bruchstücke wie beim Neobroker
            shares = math.floor(budget / price * 10000) / 10000
        return shares if shares * price >= MIN_ORDER else 0

    def buy(self, sym: str, day: str, price: float, stop: float | None, target: float | None, reason: str,
            profile: analysis.Profile, equity: float) -> dict | None:
        if sym in self.pos or self.sold_on.get(sym) == day:
            return None
        shares = self.size(price, stop, profile, equity)
        if not shares:
            return None
        cost = shares * price + self.fee
        self.cash -= cost
        self.pos[sym] = {"symbol": sym, "shares": shares, "entry": _r(price), "entry_day": day, "cost": round(cost, 2),
                         "stop": _r(stop), "target": _r(target), "checked_day": day, "reason": reason}
        t = {"symbol": sym, "side": "buy", "shares": shares, "price": _r(price), "fee": self.fee, "day": day,
             "reason": reason, "pl": None, "pl_pct": None}
        self.trades.append(t)
        return t

    def sell(self, sym: str, day: str, price: float, reason: str) -> dict:
        p = self.pos.pop(sym)
        proceeds = p["shares"] * price - self.fee
        self.cash += proceeds
        pl = proceeds - p["cost"]
        t = {"symbol": sym, "side": "sell", "shares": p["shares"], "price": _r(price), "fee": self.fee, "day": day,
             "reason": reason, "pl": round(pl, 2), "pl_pct": round(pl / p["cost"] * 100, 2) if p["cost"] else None}
        self.sold_on[sym] = day
        self.trades.append(t)
        return t


def check_exit(p: dict, o: float | None, h: float, low: float) -> tuple[float, str] | None:
    """Stopp oder Ziel innerhalb einer Tageskerze? Bei einer Kurslücke wird zur Eröffnung gehandelt."""
    stop, target = p.get("stop"), p.get("target")
    if stop is not None and low <= stop:
        price = min(o, stop) if o and o > 0 else stop
        return price, ("Nachgezogener Stopp erreicht, Gewinn gesichert" if price > p["entry"] else "Stopp erreicht")
    if target and h >= target:
        price = max(o, target) if o and o > 0 else target
        return price, "Kursziel erreicht"
    return None


def trail(p: dict, sig: Sig, profile: analysis.Profile) -> None:
    if sig.atr:
        new = sig.close - profile.h["stop_atr"] * sig.atr
        if p.get("stop") is None or new > p["stop"]:
            p["stop"] = _r(new)


def _bars(df: pd.DataFrame) -> dict[str, tuple[float, float, float, float]]:
    out = {}
    for t, o, h, lo, c in zip(df.index, df["open"], df["high"], df["low"], df["close"], strict=True):
        if pd.isna(c):
            continue
        c = float(c)
        out[day_of(t)] = (float(o) if not pd.isna(o) else c, float(h) if not pd.isna(h) else c,
                          float(lo) if not pd.isna(lo) else c, c)
    return out


# ---------- Rückblick ----------

def precompute(histories: dict[str, pd.DataFrame], days: list[str], progress=None) -> dict:
    """Signale aller neun Varianten für jeden Tag. Indikatoren nur einmal je Wert, Analyse einmal je Horizont."""
    sigs: dict[tuple[str, str], dict[str, dict[str, Sig]]] = {(h, r): {} for h in HORIZONS for r in RISKS}
    wanted = set(days)
    total = max(1, len(histories) * len(HORIZONS))
    step = 0
    for sym, df in histories.items():
        d = ind.add_all(df)
        idx = [(i, day_of(t)) for i, t in enumerate(d.index)]
        for h in HORIZONS:
            base = analysis.Profile(h, "balanced")
            for i, dd in idx:
                if i < WARMUP or dd not in wanted:
                    continue
                try:
                    a = analysis.analyze(sym, d.iloc[max(0, i - 300): i + 1], base, with_breakout=False)  # 300 Kerzen reichen für alle Kennzahlen
                except ValueError:
                    continue
                for r in RISKS:
                    rec = analysis.recommend(a, None, analysis.Profile(h, r))
                    sigs[(h, r)].setdefault(sym, {})[dd] = to_sig(a, rec)
            step += 1
            if progress:
                progress(step / total)
    return sigs


def simulate(variant: tuple[str, str], sigs: dict[str, dict[str, Sig]], bars: dict[str, dict], days: list[str],
             capital: float, fee: float) -> dict:
    profile = analysis.Profile(*variant)
    book = Book(capital, fee)
    last: dict[str, float] = {}
    pending: dict[str, tuple] = {}
    curve: list[tuple[str, float]] = []
    for dd in days:
        # 1. Aufträge vom Vortag zur Eröffnung ausführen (erst Verkäufe, dann Käufe nach Stärke)
        for sym, order in sorted(pending.items(), key=lambda kv: (kv[1][0] != "sell", -kv[1][1].score
                                                                   if kv[1][0] == "buy" else 0)):
            bar = bars[sym].get(dd)
            if bar is None:
                continue
            del pending[sym]
            o = bar[0]
            if order[0] == "sell":
                if sym in book.pos:
                    book.sell(sym, dd, o, order[2])
            else:
                sg: Sig = order[1]
                shift = o - sg.close
                stop = sg.stop + shift if sg.stop is not None else None
                target = sg.target + shift if sg.target is not None else None
                book.buy(sym, dd, o, stop, target, sg.reason, profile, book.value(last))
        # 2. Stopp und Ziel im Tagesverlauf
        for sym in list(book.pos):
            bar = bars[sym].get(dd)
            if bar is None:
                continue
            ex = check_exit(book.pos[sym], bar[0], bar[1], bar[2])
            if ex:
                book.sell(sym, dd, ex[0], ex[1])
        # 3. Schlusskurse und neue Signale
        for sym, per_day in sigs.items():
            bar = bars[sym].get(dd)
            if bar is None:
                continue
            last[sym] = bar[3]
            sg = per_day.get(dd)
            if sg is None:
                continue
            if sym in book.pos:
                trail(book.pos[sym], sg, profile)
                if sg.action == SELL:
                    pending[sym] = ("sell", sg, f"Einschätzung auf Vorsicht gekippt: {sg.reason}")
            elif sg.action == BUY and book.sold_on.get(sym) != dd:
                pending[sym] = ("buy", sg)
            else:
                pending.pop(sym, None)
        curve.append((dd, round(book.value(last), 2)))
    return {"curve": curve, "trade_log": book.trades, "open": len(book.pos), **stats(curve, capital, book.trades)}


def stats(curve: list[tuple[str, float]], capital: float, trades: list[dict]) -> dict:
    end = curve[-1][1] if curve else capital
    peak, mdd = capital, 0.0
    for _, v in curve:
        peak = max(peak, v)
        mdd = min(mdd, (v / peak - 1) * 100 if peak else 0)
    sells = [t for t in trades if t["side"] == "sell"]
    wins = [t for t in sells if (t["pl"] or 0) > 0]
    return {"end_value": round(end, 2), "return_pct": round((end / capital - 1) * 100, 2),
            "max_drawdown_pct": round(mdd, 2), "trades": len(sells), "buys": sum(t["side"] == "buy" for t in trades),
            "win_rate": round(len(wins) / len(sells) * 100, 1) if sells else None}


def buy_and_hold(bars: dict[str, dict], days: list[str], capital: float, fee: float) -> dict:
    """Vergleich: am ersten Tag alles gleichmäßig auf die Werte verteilen und liegen lassen."""
    syms = [s for s, b in bars.items() if any(d in b for d in days[:10])]
    if not syms or not days:
        return {"curve": [], **stats([], capital, [])}
    part = capital / len(syms)
    shares, cash, last = {}, capital, {}
    curve = []
    for dd in days:
        for s in syms:
            bar = bars[s].get(dd)
            if bar is None:
                continue
            last[s] = bar[3]
            if s not in shares and part - fee > 0:
                shares[s] = (part - fee) / bar[0]
                cash -= part
        curve.append((dd, round(cash + sum(n * last.get(s, 0) for s, n in shares.items()), 2)))
    return {"curve": curve, **stats(curve, capital, [])}


def _pc(x: float) -> str:
    return f"{x:+.1f}".replace(".", ",").replace("-", "−") + " %"


def label(variant: tuple[str, str]) -> str:
    return analysis.Profile(*variant).label


def backtest(histories: dict[str, pd.DataFrame], capital: float, fee: float, current: tuple[str, str],
             years: int = 2, progress=None, end: date | None = None) -> dict:
    end = end or date.today()
    start = (end - timedelta(days=365 * years)).isoformat()
    bars = {s: _bars(df) for s, df in histories.items()}
    days = sorted({d for b in bars.values() for d in b if d >= start})
    if len(days) < 60:
        raise ValueError("Zu wenig Kursdaten für einen Rückblick (mindestens drei Jahre Historie nötig).")
    mid = days[len(days) // 2]
    phases = {"learn": [d for d in days if d < mid], "test": [d for d in days if d >= mid]}
    sigs = precompute(histories, days, progress)
    rows = []
    for v in sigs:
        row = {"horizon": v[0], "risk": v[1], "label": label(v), "current": v == current}
        for ph, ds in phases.items():
            res = simulate(v, sigs[v], bars, ds, capital, fee)
            row[ph] = {k: res[k] for k in ("end_value", "return_pct", "max_drawdown_pct", "trades", "buys", "win_rate", "open")}
            row[f"_{ph}"] = res
        rows.append(row)
    bench = {ph: buy_and_hold(bars, ds, capital, fee) for ph, ds in phases.items()}

    def rank(r):  # Rendite zählt, ein tiefer Einbruch kostet etwas
        return r["learn"]["return_pct"] + 0.25 * r["learn"]["max_drawdown_pct"]

    rows.sort(key=rank, reverse=True)
    best = rows[0]
    cur = next(r for r in rows if r["current"])
    b_test = bench["test"]["return_pct"]
    if best is cur:
        verdict = "keep"
        text = (f"Deine eingestellte Strategie ({cur['label']}) war in der Lernphase die beste Variante. "
                f"In der Prüfphase: {_pc(cur['test']['return_pct'])}.")
    elif best["test"]["return_pct"] > cur["test"]["return_pct"] + 1:
        verdict = "switch"
        text = (f"„{best['label']}“ war in der Lernphase vorn und hat auch in der Prüfphase besser abgeschnitten "
                f"als deine Strategie ({_pc(best['test']['return_pct'])} gegenüber {_pc(cur['test']['return_pct'])}). "
                "Ein Wechsel ist einen Versuch wert – passt die Variante auch zu deiner Risikobereitschaft?")
    else:
        verdict = "keep"
        text = (f"„{best['label']}“ war in der Lernphase vorn, in der Prüfphase aber nicht besser als deine Strategie "
                f"({_pc(best['test']['return_pct'])} gegenüber {_pc(cur['test']['return_pct'])}). Der Vorsprung war "
                "wohl Zufall – bleib bei deiner Einstellung.")
    text += f" Zum Vergleich: alles kaufen und liegen lassen brachte in der Prüfphase {_pc(b_test)}."

    def points(curve):
        return [{"time": d, "value": round(v - capital, 2)} for d, v in curve]

    names = {s: s for s in histories}
    out = {
        "created": datetime.now(BERLIN).isoformat(timespec="minutes"),
        "capital": capital, "fee": fee,
        "learn": {"from": phases["learn"][0], "to": phases["learn"][-1]},
        "test": {"from": phases["test"][0], "to": phases["test"][-1]},
        "symbols": list(names),
        "benchmark": {ph: {k: v for k, v in bench[ph].items() if k != "curve"} for ph in phases},
        "variants": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows],
        "best": {"horizon": best["horizon"], "risk": best["risk"], "label": best["label"]},
        "verdict": verdict, "text": text,
        "curves": {"best": points(best["_test"]["curve"]), "current": points(cur["_test"]["curve"]),
                   "benchmark": points(bench["test"]["curve"])},
        "best_trades": best["_test"]["trade_log"][-40:][::-1],
    }
    return out


# ---------- Hintergrund-Rückblick ----------

_BTS: dict[int, dict] = {}  # Fortschritt je Nutzer
_BT_LOCK = threading.Lock()  # immer nur ein Rückblick gleichzeitig (schont CPU und Kursquellen)


def _bt(uid: int) -> dict:
    return _BTS.setdefault(uid, {"status": "idle", "progress": 0.0, "error": None})


def backtest_status(uid: int = 1) -> dict:
    return dict(_bt(uid))


def _target(settings) -> str | None:
    c = settings.display_currency
    return None if not c or c == "native" else c


def run_backtest(storage, settings) -> None:
    """Lädt fünf Jahre Kurse aller Watchlist-Werte und rechnet den Rückblick. Ergebnis in paper_state."""
    _BT = _bt(storage.uid)
    _BT_LOCK.acquire()  # wartet, falls gerade ein anderer Nutzer rechnet
    try:
        _BT.update(status="running", progress=0.0, error=None)
        target = _target(settings)
        histories, skipped = {}, {}
        rows = storage.watchlist()
        for n, w in enumerate(rows):
            try:
                df = market.get_history(w["symbol"], "5y", "1d", currency=target)
                if len(df) < WARMUP + 120:
                    skipped[w["symbol"]] = "zu kurze Kurshistorie"
                    continue
                histories[w["symbol"]] = df
            except Exception as exc:  # noqa: BLE001
                skipped[w["symbol"]] = str(exc)[:120]
            _BT["progress"] = 0.2 * (n + 1) / max(1, len(rows))
        if not histories:
            raise ValueError("Keine Werte mit ausreichender Kurshistorie in der Watchlist.")
        current = (settings.invest_horizon, settings.risk_profile)
        res = backtest(histories, float(settings.paper_capital), float(settings.paper_fee), current,
                       progress=lambda f: _BT.__setitem__("progress", 0.2 + 0.8 * f))
        names = {w["symbol"]: w.get("name") or w.get("ticker") or w["symbol"] for w in rows}
        res["names"] = {s: names.get(s, s) for s in histories}
        res["skipped"] = {names.get(s, s): v for s, v in skipped.items()}
        res["currency"] = target
        storage.set_paper_state(backtest=json.dumps(res))
        _BT.update(status="done", progress=1.0)
    except Exception as exc:  # noqa: BLE001
        log.exception("Rückblick fehlgeschlagen")
        _BT.update(status="error", error=str(exc)[:300])
    finally:
        _BT_LOCK.release()


def start_backtest(storage, settings) -> bool:
    _BT = _bt(storage.uid)
    if _BT["status"] == "running":
        return False
    _BT.update(status="running", progress=0.0, error=None)
    threading.Thread(target=run_backtest, args=(storage, settings), daemon=True).start()
    return True


def last_backtest(storage) -> dict | None:
    raw = storage.paper_state().get("backtest")
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None


# ---------- Live ----------

_LIVE_LOCK = threading.Lock()


def _state(storage) -> dict:
    st = storage.paper_state()
    return {k: v for k, v in st.items() if k != "backtest"}


def start_live(storage, settings, histories: dict[str, pd.DataFrame] | None = None) -> dict:
    st = _state(storage)
    if "started" in st:
        return st
    cap = float(settings.paper_capital)
    target = _target(settings)
    bench = {}
    for w in storage.watchlist():
        try:
            df = (histories or {}).get(w["symbol"])
            if df is None:
                df = market.get_history(w["symbol"], "1mo", "1d", currency=target)
            bench[w["symbol"]] = float(df["close"].iloc[-1])
        except Exception:  # noqa: BLE001
            continue
    storage.set_paper_state(started=today(), capital=cap, cash=cap, currency=target or "native",
                            bench=json.dumps(bench))
    storage.set_paper_equity(today(), cap, cap)
    return _state(storage)


LIMIT_SLACK = 0.01  # Kauf-Limit: höchstens 1 % über dem letzten Schlusskurs (keine Kurslücken hinterherkaufen)


def market_open(symbol: str, quote: dict | None) -> bool:
    """Wird gerade gehandelt? gettex: Mo–Fr 8–22 Uhr. Sonst: frischer Kurs (höchstens 20 Minuten alt)."""
    now = datetime.now(BERLIN)
    if symbol.upper().endswith(".GTX"):
        return now.weekday() < 5 and 8 <= now.hour < 22
    t = (quote or {}).get("time")
    return bool(t) and now.timestamp() - t < 20 * 60 + 60 * ((quote or {}).get("delay_min") or 0)


def _load(storage, settings):
    st = start_live(storage, settings)
    currency = None if st.get("currency") in (None, "native") else st["currency"]
    book = Book(float(st["capital"]), float(settings.paper_fee))
    book.cash = float(st["cash"])
    book.pos = {p["symbol"]: p for p in storage.paper_positions()}
    day = today()
    for t in storage.paper_trades(200):
        if t["side"] == "sell" and t["day"] == day:
            book.sold_on.setdefault(t["symbol"], day)
    names = {w["symbol"]: w.get("name") or w.get("ticker") or w["symbol"] for w in storage.watchlist()}
    return currency, book, names


def _quote(sym: str, currency: str | None) -> dict | None:
    try:
        q = market.live(sym, currency)
        return q if q.get("price") else None
    except Exception:  # noqa: BLE001
        return None


def _persist(storage, settings, book: Book, n_before: int, names: dict, push: bool | None) -> list[dict]:
    new = book.trades[n_before:]
    stored = {p["symbol"] for p in storage.paper_positions()}
    for sym in stored - set(book.pos):
        storage.remove_paper_position(sym)
    for p in book.pos.values():
        storage.save_paper_position(p)
    for t in new:
        storage.add_paper_trade(t)
    storage.set_paper_state(cash=round(book.cash, 2))
    if new and (settings.paper_notify if push is None else push):
        lines = []
        for t in new:
            verb = "Kauf" if t["side"] == "buy" else "Verkauf"
            res = f" ({t['pl']:+.2f}, {t['pl_pct']:+.1f} %)".replace(".", ",") if t["pl"] is not None else ""
            lines.append(f"**{verb} {names.get(t['symbol'], t['symbol'])}**: {t['shares']:g} × "
                         f"{t['price']:.2f}".replace(".", ",") + f"{res} – {t['reason']}")
        notify.send(settings, "Schattendepot", "\n".join(lines), tags=["robot"], path="/depot/schatten")
    return new


def _buy_now(book: Book, sym: str, day: str, price: float, ref: float, stop: float | None, target: float | None,
             reason: str, profile, equity: float) -> dict | None:
    """Kauf zum aktuellen Kurs; Stopp und Ziel behalten ihren Abstand zum Kurs, auf den sich das Signal bezog."""
    shift = price - ref if ref else 0
    return book.buy(sym, day, price, stop + shift if stop is not None else None,
                    target + shift if target is not None else None, reason, profile, equity)


def check_orders(storage, settings, push: bool | None = None) -> dict:
    """Offene Orders und Stopps/Ziele mit Live-Kursen prüfen (läuft im Handelsverlauf alle paar Minuten)."""
    with _LIVE_LOCK:
        if "started" not in _state(storage):
            return {"trades": [], "orders": 0}
        currency, book, names = _load(storage, settings)
        profile = analysis.profile_from(settings)
        n_before = len(book.trades)
        day = today()
        orders = storage.paper_orders(status="open")
        syms = {o["symbol"] for o in orders} | set(book.pos)
        quotes = {s: _quote(s, currency) for s in syms}
        prices = {s: q["price"] for s, q in quotes.items() if q}
        for o in orders:
            sym, q = o["symbol"], quotes.get(o["symbol"])
            if o["side"] == "buy" and o["day"] < day:
                storage.close_paper_order(o["id"], "cancelled", "Tag vorbei, Limit nicht erreicht")
                continue
            if not q or not market_open(sym, q):
                continue
            if o["side"] == "sell":
                if sym in book.pos:
                    book.sell(sym, day, q["price"], o["reason"])
                    storage.close_paper_order(o["id"], "filled", f"zu {q['price']:.2f}".replace(".", ","))
                else:
                    storage.close_paper_order(o["id"], "cancelled", "nicht mehr im Depot")
            elif q["price"] <= (o["limit_price"] or 0):
                t = _buy_now(book, sym, day, q["price"], o["ref_price"], o["stop"], o["target"], o["reason"], profile,
                             book.value(prices))
                storage.close_paper_order(o["id"], "filled" if t else "cancelled",
                                          f"zu {q['price']:.2f}".replace(".", ",") if t else "zu wenig freies Geld")
        # Stopp- und Zielorders der offenen Positionen
        for sym in list(book.pos):
            q = quotes.get(sym)
            if not q or not market_open(sym, q):
                continue
            p = book.pos[sym]
            ex = check_exit(p, None, q["price"], q["price"])
            if ex:
                book.sell(sym, day, q["price"], ex[1] + " (Order)")
        new = _persist(storage, settings, book, n_before, names, push)
        return {"trades": new, "orders": len(storage.paper_orders(status="open"))}


def run_live(storage, settings, push: bool | None = None) -> dict:
    """Ein Handelslauf (zu den Berichtszeiten). Ist der Markt offen, wird sofort zum aktuellen Kurs gehandelt;
    sonst werden Orders platziert: Kauf-Limit knapp über dem letzten Schlusskurs (gilt bis Handelsende),
    Verkauf zur Eröffnung. Stopp und Ziel jeder Position wirken wie Stop- bzw. Limit-Orders."""
    check_orders(storage, settings, push)
    with _LIVE_LOCK:
        currency, book, names = _load(storage, settings)
        profile = analysis.profile_from(settings)
        day = today()
        n_before = len(book.trades)
        symbols = list(dict.fromkeys(list(names) + list(book.pos)))
        open_orders = storage.paper_orders(status="open")

        errors, sigs, bars, prices, quotes = {}, {}, {}, {}, {}
        period = "2y" if profile.period == "2y" else "1y"
        for sym in symbols:
            try:
                df = market.get_history(sym, period, "1d", currency=currency)
                a = analysis.analyze(sym, df, profile)
                items = news.collect(sym, settings, names.get(sym)) if sym in names else []
                rec = analysis.recommend(a, news.aggregate_sentiment(items), profile)
                sigs[sym] = to_sig(a, rec)
                bars[sym] = _bars(df)
                prices[sym] = a.last_close
                quotes[sym] = _quote(sym, currency)
                if quotes[sym]:
                    prices[sym] = quotes[sym]["price"]
            except Exception as exc:  # noqa: BLE001
                errors[sym] = str(exc)[:160]

        # Stopps und Ziele an den Tageskerzen seit dem letzten Lauf prüfen, dann Stopp nachziehen und Signale
        new_orders = []
        for sym in list(book.pos):
            p = book.pos[sym]
            if sym not in bars:
                continue
            for dd in sorted(d for d in bars[sym] if d > p["checked_day"]):
                o, h, lo, _ = bars[sym][dd]
                ex = check_exit(p, o, h, lo)
                if ex:
                    book.sell(sym, dd, ex[0], ex[1])
                    break
            if sym not in book.pos:
                continue
            p["checked_day"] = max(bars[sym]) if bars[sym] else day
            trail(p, sigs[sym], profile)
            if sigs[sym].action == SELL:
                reason = f"Einschätzung auf Vorsicht gekippt: {sigs[sym].reason}"
                if market_open(sym, quotes.get(sym)):
                    book.sell(sym, day, prices[sym], reason)
                elif not any(o["symbol"] == sym and o["side"] == "sell" for o in open_orders):
                    new_orders.append({"symbol": sym, "side": "sell", "kind": "open", "reason": reason, "day": day})

        # Alte Kauf-Orders durch neue ersetzen
        for o in open_orders:
            if o["side"] == "buy":
                storage.close_paper_order(o["id"], "cancelled", "durch neuen Lauf ersetzt")
        cands = sorted((s for s in sigs if s in names and s not in book.pos and sigs[s].action == BUY),
                       key=lambda s: -sigs[s].score)
        for sym in cands:
            sg = sigs[sym]
            if book.sold_on.get(sym) == day:
                continue
            if market_open(sym, quotes.get(sym)):
                t = _buy_now(book, sym, day, prices[sym], sg.close, sg.stop, sg.target, sg.reason, profile,
                             book.value(prices))
                if t:
                    book.pos[sym]["checked_day"] = max(bars[sym]) if bars[sym] else day
            else:
                new_orders.append({"symbol": sym, "side": "buy", "kind": "limit", "day": day, "ref_price": sg.close,
                                   "limit_price": round(sg.close * (1 + LIMIT_SLACK), 4), "stop": sg.stop,
                                   "target": sg.target, "reason": sg.reason})
        for o in new_orders:
            storage.add_paper_order(o)

        new = _persist(storage, settings, book, n_before, names, push)
        equity = book.value(prices)
        storage.set_paper_state(last_run=datetime.now(BERLIN).isoformat(timespec="minutes"))
        storage.set_paper_equity(day, round(equity, 2), round(book.cash, 2))
        return {"trades": new, "orders": new_orders, "errors": errors, "equity": round(equity, 2)}


def view(storage, settings) -> dict:
    """Stand des Schattendepots mit aktuellen Kursen."""
    st = _state(storage)
    if "started" not in st:
        return {"started": False, "capital": settings.paper_capital, "fee": settings.paper_fee}
    currency = None if st.get("currency") in (None, "native") else st["currency"]
    names = {w["symbol"]: w for w in storage.watchlist()}
    capital, cash = float(st["capital"]), float(st["cash"])
    positions, value = [], cash
    for p in storage.paper_positions():
        price = None
        try:
            price = float(market.get_history(p["symbol"], "1mo", "1d", currency=currency)["close"].iloc[-1])
        except Exception:  # noqa: BLE001
            pass
        cur = price if price is not None else p["entry"]
        val = p["shares"] * cur
        value += val
        w = names.get(p["symbol"], {})
        positions.append({**p, "name": w.get("name"), "ticker": w.get("ticker"), "price": _r(price), "value": round(val, 2),
                          "pl": round(val - p["cost"], 2), "pl_pct": round((val / p["cost"] - 1) * 100, 2) if p["cost"] else None})
    trades = storage.paper_trades()
    for t in trades:
        w = names.get(t["symbol"], {})
        t["name"], t["ticker"] = w.get("name"), w.get("ticker")
    sells = [t for t in trades if t["side"] == "sell"]
    curve = [{"time": e["day"], "value": round(e["equity"] - capital, 2)} for e in storage.paper_equity()]
    if curve and curve[-1]["time"] == today():
        curve[-1]["value"] = round(value - capital, 2)
    elif curve:
        curve.append({"time": today(), "value": round(value - capital, 2)})
    bench = None
    try:
        start = json.loads(st.get("bench") or "{}")
        rel = []
        for sym, p0 in start.items():
            try:
                rel.append(float(market.get_history(sym, "1mo", "1d", currency=currency)["close"].iloc[-1]) / p0)
            except Exception:  # noqa: BLE001
                continue
        bench = round((sum(rel) / len(rel) - 1) * 100, 2) if rel else None
    except ValueError:
        pass
    return {
        "started": st["started"], "last_run": st.get("last_run"), "capital": capital, "cash": round(cash, 2),
        "currency": currency, "fee": settings.paper_fee, "value": round(value, 2),
        "pl": round(value - capital, 2), "pl_pct": round((value / capital - 1) * 100, 2),
        "realized": round(sum(t["pl"] or 0 for t in sells), 2),
        "win_rate": round(sum((t["pl"] or 0) > 0 for t in sells) / len(sells) * 100, 1) if sells else None,
        "trades_count": len(sells), "benchmark_pct": bench,
        "positions": positions, "trades": trades, "curve": curve,
        "orders": [{**o, "name": names.get(o["symbol"], {}).get("name"), "ticker": names.get(o["symbol"], {}).get("ticker")}
                   for o in storage.paper_orders(limit=40)],
    }
