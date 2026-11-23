"""Gesamtportfolio: alle Depots zusammen – hochgeladene Bestände, importierte und manuell erfasste Käufe.

Doppelzählung wird vermieden: Käufe, die einem Bankdepot zugeordnet sind, stecken schon in dessen Bestand und zählen
dort. Manuell erfasste Käufe ohne Depot werden einem Depot zugeordnet, wenn dessen hochgeladene Bestandsliste denselben
Wert (ISIN) mit mindestens dieser Stückzahl enthält.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import date

from . import analysis, gettex, market, marketstore, portfolio
from .brokers import BANKS, COUNTRIES, country_of

_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="wealth")
TYPE_LABELS = {"Aktie": "Aktien", "EQUITY": "Aktien", "ETF/Fonds": "ETFs & Fonds", "ETF": "ETFs & Fonds",
               "MUTUALFUND": "ETFs & Fonds", "CRYPTOCURRENCY": "Krypto", "INDEX": "Indizes", "CURRENCY": "Devisen",
               "FUTURE": "Rohstoffe", "BOND": "Anleihen"}


def _isin(symbol: str | None) -> str | None:
    if symbol and gettex.is_gettex(symbol):
        return gettex.isin_of(symbol)
    return None


def _price(symbol: str, ccy: str) -> dict | None:
    try:
        return market.live(symbol, ccy)
    except Exception:  # noqa: BLE001
        return None


def _type_label(symbol: str | None, isin: str | None, name: str | None) -> str:
    info = market.cached_info(symbol) if symbol else None
    t = (info or {}).get("type")
    if t in TYPE_LABELS:
        return TYPE_LABELS[t]
    n = (name or "").lower()
    if any(w in n for w in ("etf", "ishares", "xtrackers", "vanguard", "amundi", "spdr", "invesco", "msci", "fonds")):
        return "ETFs & Fonds"
    if isin and isin[:2] in ("IE", "LU") and not t:
        return "ETFs & Fonds"
    return "Aktien" if isin else "Sonstiges"


def auto_assign(storage, account_id: int, holdings: list[dict]) -> int:
    """Manuelle Käufe ohne Depot einem Bankdepot zuordnen, wenn die Bank den Wert mit genug Stück meldet."""
    by_isin = {h["isin"]: h["quantity"] for h in holdings if h.get("isin")}
    n = 0
    open_ = [p for p in storage.positions(open_only=True) if not p.get("account_id")]
    groups: dict[str, list[dict]] = {}
    for p in open_:
        isin = _isin(p["symbol"])
        if isin and isin in by_isin:
            groups.setdefault(isin, []).append(p)
    for isin, ps in groups.items():
        if sum(p["quantity"] for p in ps) <= by_isin[isin] + 1e-6:
            for p in ps:
                storage.update_position(p["id"], {"account_id": account_id})
                n += 1
    return n


def overview(storage, settings, budget: float = 1.4) -> dict:
    ccy = settings.display_currency if settings.display_currency in market.CURRENCIES else "EUR"
    profile = analysis.profile_from(settings)
    accounts = {a["id"]: a for a in storage.broker_accounts()}
    holdings = storage.holdings()
    bank_accounts = {h["account_id"] for h in holdings}
    lines: list[dict] = []

    # Kurse parallel holen (meist aus dem Speicher); was im Budget nicht kommt, nimmt den Wert der Bank
    syms = sorted({h["symbol"] for h in holdings if h.get("symbol")})
    futs = {_POOL.submit(_price, s, ccy): s for s in syms}
    done, _ = wait(list(futs), timeout=budget) if futs else (set(), set())
    prices = {futs[f]: f.result() for f in done if f.result()}

    for h in holdings:
        acc = accounts.get(h["account_id"]) or {}
        q = prices.get(h.get("symbol") or "")
        qty = float(h["quantity"])
        bank_ccy = h.get("currency") or "EUR"
        if q and q.get("price"):
            price, change = q["price"], q.get("change_pct")
        else:
            price = h.get("price")
            if price is not None and bank_ccy != ccy:
                try:
                    price = market.convert_price(price, bank_ccy, ccy)
                except market.MarketDataError:
                    pass
            change = None
        value = qty * price if price is not None else h.get("value")
        cost = qty * h["avg_price"] if h.get("avg_price") else None
        lines.append({
            "source": "bank", "account_id": h["account_id"], "account": acc.get("label") or acc.get("bank"),
            "symbol": h.get("symbol"), "isin": h.get("isin"), "name": h.get("name"), "quantity": qty,
            "price": round(price, 4) if price is not None else None, "value": round(value, 2) if value else None,
            "cost": round(cost, 2) if cost else None,
            "pl": round(value - cost, 2) if value and cost else None,
            "pl_pct": round((value / cost - 1) * 100, 2) if value and cost else None,
            "day_change_pct": change, "as_of": h.get("as_of"), "updated_at": h.get("updated_at"),
        })

    # Käufe (manuell oder importiert), die nicht in einem Bankbestand stecken
    groups: dict[tuple, list[dict]] = {}
    for p in storage.positions(open_only=True):
        if p.get("account_id") in bank_accounts:
            continue
        groups.setdefault((p.get("account_id"), p["symbol"]), []).append(p)
    t0 = time.time()
    for (acc_id, sym), ps in groups.items():
        # nach Ablauf des Budgets nur noch Einstand zeigen (Kurs folgt beim nächsten Laden aus dem Speicher)
        evs = [portfolio.evaluate(p, profile) for p in ps] if time.time() - t0 <= budget else []
        acc = accounts.get(acc_id) or {}
        qty = sum(p["quantity"] for p in ps)
        value = cost = 0.0
        known = True
        change = None
        name = ps[0].get("note") or sym
        for ev in evs:
            c = ev.get("display_currency")
            try:
                v = market.convert_price(ev["value"], c, ccy) if c and ev.get("value") is not None else ev.get("value")
                k = market.convert_price(ev["invested"], c, ccy) if c else ev["invested"]
            except market.MarketDataError:
                v, k = ev.get("value"), ev["invested"]
            if v is None:
                known = False
            value += v or 0
            cost += k or 0
            change = ev.get("day_change_pct", change)
            name = ev.get("name") or name
        if not evs:
            known = False
            cost = sum(portfolio.cost(p) for p in ps)
        lines.append({
            "source": "import" if acc_id else "manual", "account_id": acc_id,
            "account": acc.get("label") or (BANKS.get(acc.get("bank"), {}).get("name") if acc else "Manuell erfasst"),
            "symbol": sym, "isin": _isin(sym), "name": name, "quantity": qty, "lots": len(ps),
            "price": round(value / qty, 4) if known and qty else None, "value": round(value, 2) if known else None,
            "cost": round(cost, 2), "pl": round(value - cost, 2) if known else None,
            "pl_pct": round((value / cost - 1) * 100, 2) if known and cost else None, "day_change_pct": change,
        })

    total = sum(x["value"] or 0 for x in lines)
    cost_known = [x for x in lines if x.get("cost") and x.get("value")]
    cost = sum(x["cost"] for x in cost_known)
    pl = sum(x["value"] - x["cost"] for x in cost_known)
    day_abs = sum((x["value"] or 0) * (x["day_change_pct"] or 0) / (100 + (x["day_change_pct"] or 0))
                  for x in lines if x.get("day_change_pct") is not None)
    for x in lines:
        x["weight"] = round((x["value"] or 0) / total * 100, 2) if total else None
        x["type"] = _type_label(x.get("symbol"), x.get("isin"), x.get("name"))
        x["country"] = country_of(x.get("isin"))
    lines.sort(key=lambda x: -(x["value"] or 0))

    def alloc(key, label=lambda k: k or "Unbekannt"):
        out: dict[str, float] = {}
        for x in lines:
            out[label(x.get(key))] = out.get(label(x.get(key)), 0) + (x["value"] or 0)
        return sorted(({"label": k, "value": round(v, 2), "pct": round(v / total * 100, 1) if total else 0}
                       for k, v in out.items() if v), key=lambda d: -d["value"])

    def country_label(code):
        if not code:
            return "Unbekannt"
        return COUNTRIES.get(code, code)

    hints = []
    if lines and total:
        top = lines[0]
        if (top["weight"] or 0) > 25:
            hints.append({"level": "warn", "text": f"{top['name']} macht {top['weight']:.0f} % des Vermögens aus – "
                                                   "ein Klumpenrisiko."})
    result = {
        "currency": ccy, "value": round(total, 2), "cost": round(cost, 2), "pl": round(pl, 2),
        "pl_pct": round(pl / cost * 100, 2) if cost else None, "day_change": round(day_abs, 2),
        "day_change_pct": round(day_abs / (total - day_abs) * 100, 2) if total and total != day_abs else None,
        "lines": lines,
        "accounts": [_account_public(a, lines) for a in accounts.values()],
        "allocation": {"account": alloc("account"), "type": alloc("type"), "country": alloc("country", country_label)},
        "hints": hints,
        "history": record(storage.uid, total),
    }
    return result


def _account_public(a: dict, lines: list[dict]) -> dict:
    bank = BANKS.get(a["bank"], {})
    mine = [x for x in lines if x.get("account_id") == a["id"]]
    return {"id": a["id"], "bank": a["bank"], "bank_name": bank.get("name", a["bank"]), "kind": a["kind"],
            "label": a["label"] or bank.get("name", a["bank"]), "status": a["status"], "last_sync": a["last_sync"],
            "last_error": a["last_error"], "positions": len(mine), "value": round(sum(x["value"] or 0 for x in mine), 2)}


def record(uid: int, value: float) -> list[dict]:
    """Tageswert des Gesamtvermögens merken (für den Verlauf auf der Startseite)."""
    store = marketstore.get_store()
    if store is None:
        return []
    key = f"wealth:{uid}"
    hist = store.get(key) or {}
    if value:
        hist[date.today().isoformat()] = round(value, 2)
        if len(hist) > 2000:
            for k in sorted(hist)[:-2000]:
                hist.pop(k, None)
        store.put(key, hist)
    return [{"day": k, "value": v} for k, v in sorted(hist.items())]
