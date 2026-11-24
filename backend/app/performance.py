"""Analyse der eigenen Anlagestrategie: Rendite (IZF/XIRR, zeitgewichtet), Vergleich mit Indizes und Handelsverhalten.

Grundlage sind alle erfassten oder importierten Käufe und Verkäufe (Tabelle positions) mit Datum. Daraus entstehen
- Zahlungsströme (Kauf = Geld rein, Verkauf = Geld raus, heutiger Wert der offenen Bestände am Ende),
- eine tägliche Wertreihe des Depots (Stückzahl am Tag × Schlusskurs, in Anzeigewährung),
- für jeden Vergleichsindex ein „Schattendepot“, das mit genau denselben Beträgen an denselben Tagen gekauft und
  verkauft hätte. So ist der Vergleich fair: gleiches Geld, gleiche Zeitpunkte, nur ein anderes Ziel.

Vergleichswerte sind thesaurierende ETFs in Euro (Gesamtrendite inklusive Dividenden), gehandelt auf Xetra.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import date, datetime

import numpy as np
import pandas as pd

from . import market, marketstore, portfolio

log = logging.getLogger(__name__)

BENCHMARKS = [
    ("EUNL.DE", "MSCI World", "iShares Core MSCI World"),
    ("EXS1.DE", "DAX", "iShares Core DAX"),
    ("SXR8.DE", "S&P 500", "iShares Core S&P 500"),
    ("SXRT.DE", "Euro Stoxx 50", "iShares Core EURO STOXX 50"),
    ("SXRV.DE", "Nasdaq 100", "iShares Nasdaq 100"),
]
BENCH_SYMBOLS = [b[0] for b in BENCHMARKS]
CACHE_TTL = 20 * 60
CALC_VERSION = 2  # erhöhen, wenn sich die Rechnung ändert (alte Ergebnisse im Speicher verfallen dann)
AFTER_DAYS = 20  # Handelstage für „was passierte nach dem Kauf / Verkauf“

_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="performance")
_RUNNING: dict[str, object] = {}
_LOCK = threading.Lock()


# ---------------------------------------------------------------- Rechenbausteine

def xirr(flows: list[tuple[date, float]]) -> float | None:
    """Interner Zinsfuß (IZF) pro Jahr für unregelmäßige Zahlungen. Einzahlung negativ, Auszahlung positiv.
    Liefert z. B. 0.084 für 8,4 % p. a.; None, wenn er nicht bestimmbar ist."""
    flows = [(d, float(v)) for d, v in flows if v and math.isfinite(v)]
    if len(flows) < 2 or not any(v < 0 for _, v in flows) or not any(v > 0 for _, v in flows):
        return None
    d0 = min(d for d, _ in flows)
    ts = [((d - d0).days / 365.0, v) for d, v in flows]
    if max(t for t, _ in ts) <= 0:
        return None

    def npv(r: float) -> float:
        return sum(v / (1 + r) ** t for t, v in ts)

    lo, hi = -0.9999, 1.0
    f_lo = npv(lo)
    # obere Grenze ausweiten, bis das Vorzeichen wechselt (sehr hohe Renditen bei kurzen Zeiträumen)
    f_hi = npv(hi)
    tries = 0
    while f_lo * f_hi > 0 and tries < 40:
        hi *= 2
        f_hi = npv(hi)
        tries += 1
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):  # Bisektion: langsam, aber verlässlich
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7 or hi - lo < 1e-9:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2


def twr(values: pd.Series, flows: pd.Series) -> pd.Series:
    """Zeitgewichtete Tagesrenditen: Ein- und Auszahlungen verzerren sie nicht.
    values: Depotwert am Tagesende; flows: am Tag eingezahlt (Käufe +, Verkäufe −).

    Käufe zählen zum Tagesbeginn (sie stehen im Nenner), Verkaufserlöse zum Tagesende (im Zähler):
        r = (Wert heute + Verkäufe) / (Wert gestern + Käufe) − 1
    So bleibt der Nenner nie winzig. Die naive Formel (Wert − Fluss) / Wert gestern explodiert, wenn ein fast leeres
    Depot an einem Tag viel nachkauft – schon 2 % Unterschied zwischen Kauf- und Schlusskurs würden sonst als
    Hunderte Prozent Verlust zählen."""
    v = values.to_numpy(dtype=float)
    f = flows.reindex(values.index).fillna(0).to_numpy(dtype=float)
    r = np.zeros(len(v))
    for i in range(len(v)):
        prev = v[i - 1] if i else 0.0
        buys, sells = max(f[i], 0.0), max(-f[i], 0.0)
        base = prev + buys
        if base > 1e-9:
            r[i] = (v[i] + sells) / base - 1
    return pd.Series(r, index=values.index)


def shadow(prices: pd.Series, values: pd.Series, flows: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Vergleichsdepot: kauft mit denselben Beträgen am selben Tag; verkauft am selben Tag denselben *Anteil*,
    den du von deinem Depot verkauft hast. Liefert (Wert je Tag, eigene Zahlungen je Tag; Kauf +, Verkauf −).
    Anteilig statt betragsgleich, weil das Vergleichsdepot sonst mehr auszahlen müsste, als es besitzt."""
    p = prices.to_numpy(dtype=float)
    v = values.to_numpy(dtype=float)
    f = flows.reindex(values.index).fillna(0).to_numpy(dtype=float)
    units = 0.0
    val = np.zeros(len(p))
    own = np.zeros(len(p))
    for i in range(len(p)):
        px = p[i]
        if not (px > 0):
            continue
        buys, sells = max(f[i], 0.0), max(-f[i], 0.0)
        if buys:
            units += buys / px
            own[i] += buys
        if sells and units > 0:
            total = v[i] + sells  # dein Depot vor dem Verkauf (zum Schlusskurs)
            share = min(sells / total, 1.0) if total > 1e-9 else 1.0
            sold = units * share
            units -= sold
            own[i] -= sold * px
        val[i] = units * px
    return val, own


def max_drawdown(index: pd.Series) -> tuple[float | None, str | None, str | None]:
    if index is None or len(index) < 2:
        return None, None, None
    peak = index.cummax()
    dd = index / peak - 1
    end = dd.idxmin()
    start = index.loc[:end].idxmax()
    return float(dd.min()), str(pd.Timestamp(start).date()), str(pd.Timestamp(end).date())


def _day(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def _naive_days(df: pd.DataFrame) -> pd.Series:
    """Schlusskurse mit Tagesdatum als Index (ohne Zeitzone, ein Wert je Tag)."""
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    s = pd.Series(df["close"].to_numpy(dtype=float), index=idx.normalize())
    return s[~s.index.duplicated(keep="last")].sort_index()


def _period_for(first: date) -> str:
    age = (date.today() - first).days
    for limit, period in ((360, "1y"), (720, "2y"), (1800, "5y")):
        if age < limit:
            return period
    return "max"


def _round(x, n=2):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), n)


# ---------------------------------------------------------------- Hauptrechnung

def compute(positions: list[dict], target: str, profile=None, bench_symbols: list[str] | None = None) -> dict:
    """Vollständige Auswertung. Reine Funktion über die Positionen; Kurse kommen aus dem Kursspeicher."""
    lots = []
    for p in positions:
        bd = _day(p.get("buy_date"))
        if not bd or not p.get("quantity") or not p.get("buy_price"):
            continue
        lots.append({**p, "_buy": bd, "_sell": _day(p.get("sell_date")), "_ccy": portfolio.position_currency(p)})
    out: dict = {"currency": target, "generated_at": int(time.time()), "lots": len(lots)}
    if not lots:
        out["empty"] = True
        return out

    first = min(lot["_buy"] for lot in lots)
    period = _period_for(first)
    symbols = sorted({lot["symbol"] for lot in lots})

    closes: dict[str, pd.Series] = {}
    native_closes: dict[str, pd.Series] = {}
    missing: list[str] = []
    for sym in symbols:
        try:
            closes[sym] = _naive_days(market.get_history(sym, period, "1d", currency=target))
            native_closes[sym] = _naive_days(market.get_history(sym, period, "1d"))
        except Exception as exc:  # noqa: BLE001
            log.info("Analyse: keine Kurse für %s (%s)", sym, exc)
            missing.append(sym)

    start = pd.Timestamp(first)
    cal = sorted({d for s in closes.values() for d in s.index if d >= start})
    if not cal:
        out.update(empty=True, missing=missing)
        return out
    cal = pd.DatetimeIndex(cal)
    last_day = cal[-1]

    def conv(amount: float, ccy: str | None, day: date) -> float:
        if not ccy or ccy == target:
            return amount
        try:
            return float(market.convert_price(amount, ccy, target, day=day))
        except Exception:  # noqa: BLE001
            return amount

    def cal_pos(d: date) -> int:
        """Handelstag, an dem ein Kauf/Verkauf zählt (Wochenende → nächster Handelstag)."""
        return min(int(cal.searchsorted(pd.Timestamp(d))), len(cal) - 1)

    values = pd.Series(0.0, index=cal)
    flows = pd.Series(0.0, index=cal)
    cash: list[tuple[date, float]] = []
    closed, open_lots = [], []
    fees_total = 0.0
    traded_volume = 0.0
    for lot in lots:
        sym = lot["symbol"]
        qty = float(lot["quantity"])
        cost_native = qty * float(lot["buy_price"]) + float(lot.get("fees") or 0)
        cost = conv(cost_native, lot["_ccy"], lot["_buy"])
        fees_total += conv(float(lot.get("fees") or 0), lot["_ccy"], lot["_buy"])
        traded_volume += cost
        cash.append((lot["_buy"], -cost))
        i0 = cal_pos(lot["_buy"])
        flows.iloc[i0] += cost
        i1 = len(cal)
        proceeds = None
        if lot["_sell"] and lot.get("sell_price") is not None:
            proceeds_native = qty * float(lot["sell_price"]) - float(lot.get("sell_fees") or 0)
            proceeds = conv(proceeds_native, lot["_ccy"], lot["_sell"])
            fees_total += conv(float(lot.get("sell_fees") or 0), lot["_ccy"], lot["_sell"])
            traded_volume += proceeds
            cash.append((lot["_sell"], proceeds))
            i1 = cal_pos(lot["_sell"])
            flows.iloc[i1] -= proceeds
        px = closes.get(sym)
        if px is not None:
            series = px.reindex(cal, method="ffill")
            if series.isna().all():
                series = pd.Series(float(lot["buy_price"]), index=cal)
            series = series.bfill()
            held = np.zeros(len(cal))
            held[i0:i1] = qty
            values = values + pd.Series(held, index=cal) * series
        else:  # ohne Kurse: zum Einstand führen
            held = np.zeros(len(cal))
            held[i0:i1] = cost
            values = values + pd.Series(held, index=cal)
        rec = {"symbol": sym, "name": lot.get("note") or sym, "buy": lot["_buy"], "sell": lot["_sell"], "qty": qty,
               "cost": cost, "buy_price": float(lot["buy_price"]), "ccy": lot["_ccy"], "stop": lot.get("stop")}
        if proceeds is not None:
            rec.update(proceeds=proceeds, sell_price=float(lot["sell_price"]))
            closed.append(rec)
        else:
            last_px = px.reindex(cal, method="ffill").iloc[-1] if px is not None and not px.empty else None
            rec["value"] = float(last_px * qty) if last_px is not None and math.isfinite(last_px) else cost
            open_lots.append(rec)

    for rec in open_lots + closed:
        try:
            info = market.cached_info(rec["symbol"]) or {}
            rec["name"] = info.get("name") or rec["name"]
        except Exception:  # noqa: BLE001
            pass

    value_now = float(values.iloc[-1])
    flows_xirr = cash + ([(last_day.date(), value_now)] if value_now > 0 else [])
    rate = xirr(flows_xirr)
    invested = sum(-v for _, v in cash if v < 0)
    withdrawn = sum(v for _, v in cash if v > 0)
    gain = value_now + withdrawn - invested
    net_in = flows.cumsum()
    peak_capital = float(net_in.max()) if len(net_in) else invested

    r = twr(values, flows)
    active = values.shift(1).fillna(0) > 1e-9
    idx = (1 + r).cumprod()
    days = max((last_day - cal[0]).days, 1)
    twr_total = float(idx.iloc[-1] - 1)
    twr_pa = (1 + twr_total) ** (365 / days) - 1 if days >= 365 else None
    vol = float(r[active].std() * math.sqrt(252)) if active.sum() > 20 else None
    mdd, mdd_from, mdd_to = max_drawdown(idx)

    # Tagessprünge über 25 % sind bei einem gestreuten Depot selten – meist ein Kursfehler oder ein falsch
    # erfasster Kauf (Preis, Stückzahl, Datum). Zur Kontrolle mitliefern.
    jumps = [{"day": str(d.date()), "pct": _round(float(x) * 100, 1)} for d, x in r.items() if abs(x) > 0.25]
    out.update(
        jumps=jumps[:10],
        period={"from": str(cal[0].date()), "to": str(last_day.date()), "days": days},
        value=_round(value_now), invested=_round(invested), withdrawn=_round(withdrawn), gain=_round(gain),
        gain_pct=_round(gain / peak_capital * 100 if peak_capital > 0 else None),
        peak_capital=_round(peak_capital), fees=_round(fees_total),
        irr=_round(rate * 100 if rate is not None else None),
        # bei weniger als einem Jahr ist „pro Jahr“ hochgerechnet und wirkt riesig – deshalb auch für den Zeitraum
        irr_period=_round(((1 + rate) ** (days / 365) - 1) * 100 if rate is not None else None),
        twr=_round(twr_total * 100), twr_pa=_round(twr_pa * 100 if twr_pa is not None else None),
        volatility=_round(vol * 100 if vol is not None else None),
        max_drawdown=_round(mdd * 100 if mdd is not None else None), drawdown_from=mdd_from, drawdown_to=mdd_to,
        missing=missing,
    )

    # ---- Vergleich mit Indizes
    benches = []
    curve = {"dates": [str(d.date()) for d in cal], "portfolio": [round(float(x) * 100, 2) for x in idx],
             "value": [round(float(x), 2) for x in values], "invested": [round(float(x), 2) for x in net_in]}
    want = bench_symbols or BENCH_SYMBOLS
    for sym, label, product in BENCHMARKS:
        if sym not in want:
            continue
        try:
            bpx = _naive_days(market.get_history(sym, period, "1d", currency=target)).reindex(cal, method="ffill").bfill()
        except Exception as exc:  # noqa: BLE001
            log.info("Analyse: Vergleich %s fehlt (%s)", sym, exc)
            continue
        if bpx.isna().all():
            continue
        rb = bpx.pct_change().fillna(0)
        b_val, b_flow = shadow(bpx, values, flows)
        b_now = float(b_val[-1])
        b_cash = [(cal[i].date(), -float(x)) for i, x in enumerate(b_flow) if abs(x) > 1e-9]
        b_rate = xirr(b_cash + ([(last_day.date(), b_now)] if b_now > 0 else []))
        b_withdrawn = -sum(x for x in b_flow if x < 0)
        # zeitgewichtet nur über die Tage, an denen das Depot investiert war (gleicher Maßstab)
        b_idx = (1 + rb.where(active | (flows > 0), 0)).cumprod()
        b_total = float(b_idx.iloc[-1] - 1)
        rr = r[active]
        rbb = rb[active]
        beta = corr = None
        if len(rr) > 30 and float(rbb.std()) > 1e-6 and float(rr.std()) > 1e-6:
            beta = float(np.cov(rr, rbb)[0, 1] / rbb.var())
            corr = float(np.corrcoef(rr, rbb)[0, 1])
        benches.append({
            "symbol": sym, "label": label, "product": product, "value": _round(b_now), "gain": _round(b_now + b_withdrawn - invested), "withdrawn": _round(b_withdrawn),
            "irr": _round(b_rate * 100 if b_rate is not None else None), "twr": _round(b_total * 100),
            "irr_period": _round(((1 + b_rate) ** (days / 365) - 1) * 100 if b_rate is not None else None),
            "diff_value": _round((value_now + withdrawn) - (b_now + b_withdrawn)), "diff_irr": _round((rate - b_rate) * 100 if rate is not None and b_rate is not None else None),
            "beta": _round(beta), "corr": _round(corr),
        })
        curve[sym] = [round(float(x) * 100, 2) for x in b_idx]
        curve[f"{sym}:value"] = [round(float(x), 2) for x in b_val]
    out["benchmarks"] = benches
    out["curve"] = _thin(curve)

    # ---- Monatsrenditen
    month = idx.resample("ME").last()
    mret = month.pct_change()
    if len(month):
        mret.iloc[0] = month.iloc[0] - 1
    out["months"] = [{"month": d.strftime("%Y-%m"), "pct": _round(v * 100)} for d, v in mret.tail(36).items()
                     if math.isfinite(v)]

    # ---- Handelsverhalten
    out["behavior"] = _behavior(closed, open_lots, native_closes, values, traded_volume, fees_total, cal, profile)
    out["years"] = _years(closed, cash)
    out["positions"] = _position_table(closed, open_lots)
    out["insights"] = _insights(out, profile)
    return out


def _thin(curve: dict, limit: int = 400) -> dict:
    n = len(curve["dates"])
    if n <= limit:
        return curve
    step = math.ceil(n / limit)
    keep = list(range(0, n, step))
    if keep[-1] != n - 1:
        keep.append(n - 1)
    return {k: [v[i] for i in keep] for k, v in curve.items()}


def _after(series: pd.Series | None, day: date, n: int) -> float | None:
    """Veränderung in % n Handelstage nach `day` (ab dem Schlusskurs des Tages)."""
    if series is None or series.empty:
        return None
    i = int(series.index.searchsorted(pd.Timestamp(day)))
    if i >= len(series) or i + n >= len(series):
        return None
    base = float(series.iloc[i])
    return (float(series.iloc[i + n]) / base - 1) * 100 if base else None


def _range_pos(series: pd.Series | None, day: date, price: float) -> float | None:
    """Wo lag der Kaufkurs in der Spanne der 250 Handelstage davor? 0 = Tief, 100 = Hoch."""
    if series is None or series.empty:
        return None
    i = int(series.index.searchsorted(pd.Timestamp(day)))
    window = series.iloc[max(0, i - 250):i]
    if len(window) < 60:
        return None
    lo, hi = float(window.min()), float(window.max())
    if hi <= lo:
        return None
    return max(0.0, min(100.0, (price - lo) / (hi - lo) * 100))


def _behavior(closed, open_lots, native, values, volume, fees, cal, profile) -> dict:
    b: dict = {"buys": len(closed) + len(open_lots), "sells": len(closed), "open": len(open_lots)}
    months = max((cal[-1] - cal[0]).days / 30.4, 1)
    b["buys_per_month"] = _round(b["buys"] / months, 1)
    b["fees_pct"] = _round(fees / volume * 100 if volume else None, 2)
    b["fees_per_trade"] = _round(fees / (b["buys"] + b["sells"]) if b["buys"] + b["sells"] else None)

    rets, wins, losses, hold_w, hold_l, after_sell, missed = [], [], [], [], [], [], 0
    for c in closed:
        pct = (c["proceeds"] / c["cost"] - 1) * 100 if c["cost"] else 0
        c["pct"], c["pl"] = pct, c["proceeds"] - c["cost"]
        c["days"] = (c["sell"] - c["buy"]).days
        rets.append(pct)
        (wins if c["pl"] > 0 else losses).append(c)
        (hold_w if c["pl"] > 0 else hold_l).append(c["days"])
        a = _after(native.get(c["symbol"]), c["sell"], AFTER_DAYS)
        if a is not None:
            after_sell.append(a)
            if a > 5:
                missed += 1
    gross_win = sum(c["pl"] for c in wins)
    gross_loss = -sum(c["pl"] for c in losses)
    b.update(
        closed=len(closed), win_rate=_round(len(wins) / len(closed) * 100 if closed else None, 0),
        avg_win=_round(np.mean([c["pct"] for c in wins]) if wins else None, 1),
        avg_loss=_round(np.mean([c["pct"] for c in losses]) if losses else None, 1),
        profit_factor=_round(gross_win / gross_loss if gross_loss > 0 else None),
        realized=_round(gross_win - gross_loss),
        hold_win_days=_round(float(np.median(hold_w)) if hold_w else None, 0),
        hold_loss_days=_round(float(np.median(hold_l)) if hold_l else None, 0),
        after_sell_pct=_round(float(np.mean(after_sell)) if after_sell else None, 1),
        sold_too_early=missed, after_sell_n=len(after_sell),
    )
    # Kaufzeitpunkte: wo in der Jahresspanne, was passierte danach
    pos, after_buy = [], []
    all_lots = closed + open_lots
    for lot in all_lots:
        s = native.get(lot["symbol"])
        rp = _range_pos(s, lot["buy"], lot["buy_price"])
        if rp is not None:
            pos.append(rp)
        a = _after(s, lot["buy"], AFTER_DAYS)
        if a is not None:
            after_buy.append(a)
    b["buy_range_pos"] = _round(float(np.mean(pos)) if pos else None, 0)
    b["after_buy_pct"] = _round(float(np.mean(after_buy)) if after_buy else None, 1)
    # Nachkaufen in Verluste: weiterer Kauf desselben Werts unter dem Kurs eines noch offenen Blocks
    avg_down = 0
    by_sym: dict[str, list] = {}
    for lot in sorted(all_lots, key=lambda x: x["buy"]):
        prior = [p for p in by_sym.get(lot["symbol"], []) if not p["sell"] or p["sell"] > lot["buy"]]
        if prior and lot["buy_price"] < min(p["buy_price"] for p in prior) * 0.97:
            avg_down += 1
        by_sym.setdefault(lot["symbol"], []).append(lot)
    b["averaged_down"] = avg_down
    # Halten: wie lange liegen offene Positionen schon, Stopps gesetzt?
    today = cal[-1].date()
    ages = [(today - o["buy"]).days for o in open_lots]
    b["open_age_days"] = _round(float(np.median(ages)) if ages else None, 0)
    b["with_stop_pct"] = _round(sum(1 for o in open_lots if o.get("stop")) / len(open_lots) * 100 if open_lots else None, 0)
    # Streuung der offenen Bestände
    by_value: dict[str, float] = {}
    for o in open_lots:
        by_value[o["symbol"]] = by_value.get(o["symbol"], 0) + max(o.get("value") or 0, 0)
    tot = sum(by_value.values())
    if tot > 0:
        w = sorted((v / tot for v in by_value.values()), reverse=True)
        b["top_weight"] = _round(w[0] * 100, 0)
        b["effective_n"] = _round(1 / sum(x * x for x in w), 1)
        top = max(by_value, key=by_value.get)
        b["top_symbol"] = top
        b["top_name"] = next((o["name"] for o in open_lots if o["symbol"] == top), top)
    b["symbols"] = len(by_value)
    # Haltedauer gegenüber dem eingestellten Anlagehorizont
    horizon = getattr(profile, "horizon", None)
    hold = [c["days"] for c in closed] or ages
    if hold and horizon:
        med = float(np.median(hold))
        want = {"short": (0, 45), "medium": (20, 240), "long": (180, 10 ** 6)}.get(horizon, (0, 10 ** 6))
        b["hold_median_days"] = _round(med, 0)
        b["horizon"] = horizon
        b["horizon_fit"] = "kürzer" if med < want[0] else "länger" if med > want[1] else "passt"
    return b


def _years(closed, cash) -> list[dict]:
    out: dict[int, dict] = {}
    for c in closed:
        y = c["sell"].year
        d = out.setdefault(y, {"year": y, "realized": 0.0, "sells": 0, "buys": 0, "invested": 0.0})
        d["realized"] += c["pl"]
        d["sells"] += 1
    for d0, v in cash:
        if v < 0:
            d = out.setdefault(d0.year, {"year": d0.year, "realized": 0.0, "sells": 0, "buys": 0, "invested": 0.0})
            d["buys"] += 1
            d["invested"] += -v
    return [{**d, "realized": _round(d["realized"]), "invested": _round(d["invested"])} for _, d in sorted(out.items())]


def _position_table(closed, open_lots) -> list[dict]:
    """Beitrag je Wert zum Gesamtergebnis (realisiert + offen)."""
    rows: dict[str, dict] = {}
    for c in closed:
        r = rows.setdefault(c["symbol"], {"symbol": c["symbol"], "name": c["name"], "realized": 0.0, "open": 0.0, "cost": 0.0, "trades": 0})
        r["realized"] += c["pl"]
        r["cost"] += c["cost"]
        r["trades"] += 1
    for o in open_lots:
        r = rows.setdefault(o["symbol"], {"symbol": o["symbol"], "name": o["name"], "realized": 0.0, "open": 0.0, "cost": 0.0, "trades": 0})
        r["open"] += (o.get("value") or 0) - o["cost"]
        r["cost"] += o["cost"]
        r["trades"] += 1
    out = []
    for r in rows.values():
        total = r["realized"] + r["open"]
        out.append({**r, "realized": _round(r["realized"]), "open": _round(r["open"]), "total": _round(total),
                    "pct": _round(total / r["cost"] * 100 if r["cost"] else None, 1), "cost": _round(r["cost"])})
    return sorted(out, key=lambda x: -(x["total"] or 0))


def _de(x, d=1, sign=False) -> str:
    """Zahl im deutschen Format: 1.234,5"""
    if x is None:
        return "–"
    text = f"{x:{'+' if sign else ''},.{d}f}"
    return text.replace(",", "\u2009").replace(".", ",").replace("\u2009", ".")


def _fmt(x, d=1):
    return _de(x, d, sign=True)


def _insights(a: dict, profile) -> list[dict]:
    """Klartext-Befunde, wichtigstes zuerst. level: good / warn / bad / info."""
    tips: list[dict] = []
    b = a.get("behavior") or {}
    world = next((x for x in a.get("benchmarks", []) if x["symbol"] == "EUNL.DE"), None)
    if world and world.get("diff_irr") is not None and a.get("irr") is not None:
        d = world["diff_irr"]
        if a["period"]["days"] < 180:
            tips.append({"level": "info", "title": "Noch kurzer Zeitraum",
                         "text": f"Seit dem ersten Kauf sind erst {a['period']['days']} Tage vergangen – Renditen pro Jahr schwanken da stark. "
                                 "Der Vergleich wird mit jedem Monat aussagekräftiger."})
        tips.append({"level": "good" if d > 0.5 else "bad" if d < -2 else "info",
                     "title": "Gegen den Weltmarkt " + ("vorne" if d > 0 else "hinten"),
                     "text": f"Mit denselben Käufen in einen MSCI-World-ETF (und anteilig gleichen Verkäufen) hättest du insgesamt "
                             f"{_de(abs(world['diff_value'] or 0), 0)} {a['currency']} {'weniger' if (world['diff_value'] or 0) > 0 else 'mehr'} – Wert heute plus Verkaufserlöse. "
                             f"Dein Zinsfuß liegt {_de(abs(d))} Prozentpunkte pro Jahr {'darüber' if d > 0 else 'darunter'}.",
                     "key": True})
    if b.get("hold_win_days") is not None and b.get("hold_loss_days") is not None and b.get("closed", 0) >= 4:
        if b["hold_loss_days"] > b["hold_win_days"] * 1.5:
            tips.append({"level": "warn", "title": "Gewinne früh mitgenommen, Verluste lange gehalten",
                         "text": f"Gewinner verkaufst du im Mittel nach {b['hold_win_days']:.0f} Tagen, Verlierer erst nach {b['hold_loss_days']:.0f}. "
                                 "Das ist der Dispositionseffekt – feste Stopps und Ziele helfen dagegen."})
        elif b["hold_win_days"] > b["hold_loss_days"] * 1.2:
            tips.append({"level": "good", "title": "Verluste begrenzt, Gewinner laufen gelassen",
                         "text": f"Verlierer trennst du im Mittel nach {b['hold_loss_days']:.0f} Tagen, Gewinner hältst du {b['hold_win_days']:.0f} Tage."})
    if b.get("after_sell_n", 0) >= 3 and b.get("after_sell_pct") is not None:
        x = b["after_sell_pct"]
        if x > 3:
            tips.append({"level": "warn", "title": "Oft zu früh verkauft",
                         "text": f"Nach deinen Verkäufen stiegen die Kurse in den folgenden {AFTER_DAYS} Handelstagen im Schnitt um {_fmt(x)} % weiter"
                                 f" – in {b['sold_too_early']} von {b['after_sell_n']} Fällen um mehr als 5 %."})
        elif x < -3:
            tips.append({"level": "good", "title": "Gutes Timing beim Verkaufen",
                         "text": f"Nach deinen Verkäufen fielen die Kurse im Schnitt um {_fmt(x)} % – du bist meist rechtzeitig raus."})
    if b.get("buy_range_pos") is not None and b.get("buys", 0) >= 4:
        x = b["buy_range_pos"]
        if x > 75:
            tips.append({"level": "info", "title": "Du kaufst nahe am Jahreshoch",
                         "text": f"Deine Kaufkurse lagen im Schnitt bei {x:.0f} % der Jahresspanne (0 = Tief, 100 = Hoch). Das passt zu Trend- und "
                                 "Ausbruchskäufen – Rücksetzer abzuwarten wäre oft günstiger."})
        elif x < 30:
            tips.append({"level": "info", "title": "Du kaufst eher Schwäche",
                         "text": f"Deine Kaufkurse lagen im Schnitt bei {x:.0f} % der Jahresspanne – du greifst gern bei fallenden Kursen zu."})
    if b.get("averaged_down", 0) >= 2:
        tips.append({"level": "warn", "title": "Nachkäufe in Verluste",
                     "text": f"{b['averaged_down']}-mal hast du einen Wert deutlich unter deinem ersten Kaufkurs nachgekauft. "
                             "Das kann sich lohnen, erhöht aber das Risiko, wenn der Trend nicht dreht."})
    if b.get("top_weight") is not None and b["top_weight"] > 30:
        tips.append({"level": "warn", "title": "Hohe Konzentration",
                     "text": f"{b.get('top_name')} macht {b['top_weight']:.0f} % deiner offenen Bestände aus – effektiv sind das nur "
                     f"{_de(b.get('effective_n') or 1)} gleich große Positionen."})
    if b.get("fees_pct") is not None and b["fees_pct"] > 0.5:
        tips.append({"level": "warn", "title": "Gebühren fressen Rendite",
                     "text": f"Die Gebühren betragen {_de(b['fees_pct'], 2)} % des gehandelten Volumens "
                             f"(Ø {_de(b.get('fees_per_trade') or 0, 2)} {a['currency']} je Order). Größere, seltenere Orders oder ein günstigerer Broker helfen."})
    if b.get("horizon_fit") in ("kürzer", "länger"):
        label = {"short": "kurzfristig", "medium": "mittelfristig", "long": "langfristig"}.get(b.get("horizon"), "")
        tips.append({"level": "info", "title": "Haltedauer passt nicht zur Strategie",
                     "text": f"Eingestellt ist „{label}“, du hältst im Mittel {b['hold_median_days']:.0f} Tage – also {b['horizon_fit']}. "
                             "Passe die Strategie in den Einstellungen an, damit die Empfehlungen zu deinem Handeln passen."})
    if b.get("with_stop_pct") is not None and b["with_stop_pct"] < 50 and b.get("open", 0) >= 2:
        tips.append({"level": "info", "title": "Wenige Stopps gesetzt",
                     "text": f"Nur {b['with_stop_pct']:.0f} % deiner offenen Positionen haben einen Stopp. TradeHelper schlägt je Wert einen vor."})
    if b.get("win_rate") is not None and b.get("profit_factor") is not None and b.get("closed", 0) >= 5:
        pf = b["profit_factor"]
        tips.append({"level": "good" if pf > 1.5 else "bad" if pf < 1 else "info", "title": f"Trefferquote {b['win_rate']:.0f} %",
                     "text": f"Ø Gewinn {_fmt(b.get('avg_win'))} %, Ø Verlust {_fmt(b.get('avg_loss'))} %. Je 1 {a['currency']} Verlust hast du "
                             f"{_de(pf, 2)} {a['currency']} Gewinn gemacht."})
    if a.get("jumps"):
        days_txt = ", ".join(f"{datetime.fromisoformat(j['day']).strftime('%d.%m.%Y')} ({_fmt(j['pct'])} %)" for j in a["jumps"][:4])
        tips.append({"level": "warn", "title": "Auffällige Tagessprünge",
                     "text": f"An diesen Tagen änderte sich dein Depot um mehr als 25 %: {days_txt}. Prüf die Käufe und "
                             "Verkäufe dieser Tage (Kurs, Stückzahl, Datum) – oft steckt ein Erfassungs- oder Kursfehler dahinter."})
    if a.get("missing"):
        tips.append({"level": "info", "title": "Nicht alle Kurse verfügbar",
                     "text": "Für " + ", ".join(a["missing"][:5]) + " fehlen Kurse; diese Werte zählen zum Einstand."})
    order = {"bad": 0, "warn": 1, "good": 2, "info": 3}
    return sorted(tips, key=lambda t: (not t.pop("key", False), order.get(t["level"], 4)))


# ---------------------------------------------------------------- Zwischenspeicher und Aufruf aus der API

def _fingerprint(positions: list[dict], target: str, horizon: str | None) -> str:
    keys = ("id", "symbol", "quantity", "buy_price", "buy_date", "fees", "sell_price", "sell_date", "sell_fees", "currency", "stop")
    raw = json.dumps([[p.get(k) for k in keys] for p in positions], default=str) + target + str(horizon) + date.today().isoformat() + f"v{CALC_VERSION}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _run(key: str, fp: str, positions, target, profile) -> dict:
    try:
        with market.fresh_reads():
            result = compute(positions, target, profile)
        result["fingerprint"] = fp
        store = marketstore.get_store()
        if store is not None:
            store.put(key, result)
        return result
    finally:
        with _LOCK:
            _RUNNING.pop(key, None)


def overview(storage, settings, budget: float = 2.5, force: bool = False) -> dict:
    """Ergebnis aus dem Speicher, sonst rechnen – höchstens `budget` Sekunden warten, danach pending."""
    from . import analysis as an

    target = settings.display_currency if settings.display_currency in market.CURRENCIES else "EUR"
    profile = an.profile_from(settings)
    positions = storage.positions()
    fp = _fingerprint(positions, target, profile.horizon)
    key = f"performance:{storage.uid}"
    store = marketstore.get_store()
    hit = store.get_with_age(key) if store is not None and not force else None
    if hit and hit[0].get("fingerprint") == fp and hit[1] < CACHE_TTL:
        return {**hit[0], "cached_at": int(time.time() - hit[1])}
    with _LOCK:
        fut = _RUNNING.get(key)
        if fut is None:
            fut = _POOL.submit(_run, key, fp, positions, target, profile)
            _RUNNING[key] = fut
    try:
        return {**fut.result(timeout=max(0.2, budget)), "cached_at": int(time.time())}
    except FutureTimeout:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("Strategie-Analyse fehlgeschlagen: %s", exc)
        return {"error": str(exc), "currency": target}
    if hit:  # alter Stand, neuer rechnet im Hintergrund
        return {**hit[0], "refreshing": True, "cached_at": int(time.time() - hit[1])}
    return {"pending": True, "currency": target}


def as_of_label(ts: int | None) -> str:
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M") if ts else ""
