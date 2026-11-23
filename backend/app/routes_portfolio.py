"""Gesamtportfolio und Depots (Upload von CSV/PDF)."""

from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import wealth
from .brokers import BANKS, importer
from .config import Settings
from .deps import auth, user_cfg, user_storage
from .storage import Storage, now_iso

router = APIRouter(dependencies=auth)
log = logging.getLogger(__name__)
MAX_FILE = 8 * 1024 * 1024


@router.get("/api/portfolio")
def portfolio_view(st: Storage = Depends(user_storage), settings: Settings = Depends(user_cfg)):
    """Alle Depots zusammen: Wert, Gewinn/Verlust, Aufteilung, Hinweise, Verlauf."""
    return wealth.overview(st, settings)


@router.get("/api/portfolio/banks")
def banks():
    return {"banks": [{"id": k, **v} for k, v in BANKS.items()]}


class AccountIn(BaseModel):
    bank: str = Field(min_length=2, max_length=30)
    label: str = Field(default="", max_length=60)


def _account_or_404(st: Storage, account_id: int) -> dict:
    a = st.broker_account(account_id)
    if not a:
        raise HTTPException(404, "Depot nicht gefunden")
    return a


@router.post("/api/portfolio/accounts", status_code=201)
def account_add(item: AccountIn, st: Storage = Depends(user_storage)):
    bank = BANKS.get(item.bank)
    if not bank:
        raise HTTPException(422, "Unbekannter Broker")
    return {"id": st.add_broker_account("import", item.bank, item.label.strip() or bank["name"], {})}


class AccountPatch(BaseModel):
    label: str = Field(min_length=1, max_length=60)


@router.patch("/api/portfolio/accounts/{account_id}")
def account_patch(account_id: int, item: AccountPatch, st: Storage = Depends(user_storage)):
    _account_or_404(st, account_id)
    st.update_broker_account(account_id, label=item.label.strip())
    return {"ok": True}


@router.delete("/api/portfolio/accounts/{account_id}")
def account_delete(account_id: int, st: Storage = Depends(user_storage)):
    """Depot und hochgeladene Bestände löschen. Importierte Käufe bleiben (ohne Zuordnung)."""
    if not st.delete_broker_account(account_id):
        raise HTTPException(404, "Depot nicht gefunden")
    return {"ok": True}


# ---------- Import (CSV/PDF) ----------

class FileIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=MAX_FILE * 2)  # Base64


class PreviewIn(BaseModel):
    files: list[FileIn] = Field(min_length=1, max_length=40)


@router.post("/api/portfolio/accounts/{account_id}/import/preview")
def import_preview(account_id: int, item: PreviewIn, st: Storage = Depends(user_storage)):
    """Dateien lesen und zeigen, was erkannt wurde – noch nichts speichern."""
    a = _account_or_404(st, account_id)
    trades, holdings, skipped, formats = [], [], [], []
    for f in item.files:
        try:
            raw = base64.b64decode(f.content, validate=False)
        except ValueError as exc:
            raise HTTPException(422, f"{f.name}: Datei nicht lesbar") from exc
        if len(raw) > MAX_FILE:
            raise HTTPException(413, f"{f.name}: Datei zu groß (höchstens 8 MB)")
        p = importer.parse_file(f.name, raw, a["bank"])
        formats.append({"file": f.name, "kind": p.kind, "trades": len(p.trades), "holdings": len(p.holdings)})
        for t in p.trades:
            d = t.to_dict()
            d["duplicate"] = st.import_seen(t.fingerprint)
            trades.append(d)
        holdings += [h.to_dict() for h in p.holdings]
        skipped += [f"{f.name}: {s}" for s in p.skipped]
    seen = set()
    uniq = []
    for t in trades:  # gleiche Abrechnung zweimal in der Auswahl
        if t["fingerprint"] in seen:
            continue
        seen.add(t["fingerprint"])
        uniq.append(t)
    return {"files": formats, "trades": uniq, "holdings": holdings, "skipped": skipped[:100]}


class CommitIn(BaseModel):
    trades: list[dict] = Field(default_factory=list, max_length=5000)
    holdings: list[dict] = Field(default_factory=list, max_length=2000)


@router.post("/api/portfolio/accounts/{account_id}/import")
def import_commit(account_id: int, item: CommitIn, st: Storage = Depends(user_storage)):
    a = _account_or_404(st, account_id)
    out: dict = {"created": 0, "closed": 0, "duplicates": 0, "problems": [], "holdings": 0}
    trades = []
    for t in item.trades:
        try:
            tr = importer.Trade(t["side"], t["isin"], float(t["quantity"]), float(t["price"]), t["day"], t.get("time"),
                                float(t.get("fees") or 0), t.get("name"), t.get("currency") or "EUR", a["bank"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(422, f"Ungültige Zeile: {exc}") from exc
        if tr.side not in (importer.BUY, importer.SELL) or not importer.valid_isin(tr.isin) or tr.quantity <= 0 \
                or tr.price <= 0 or not importer.parse_day(tr.day):
            raise HTTPException(422, f"Ungültige Zeile: {tr.isin} {tr.day}")
        trades.append(tr.to_dict())
    if trades:
        out.update(importer.apply_trades(st, trades, account_id, f"Import {a['label'] or a['bank']}"))
    if item.holdings:
        rows = []
        for h in item.holdings:
            isin = str(h.get("isin") or "").upper()
            if not importer.valid_isin(isin):
                continue
            rows.append({"isin": isin, "symbol": f"{isin}.GTX", "name": h.get("name") or isin,
                         "quantity": float(h.get("quantity") or 0), "price": h.get("price"), "value": h.get("value"),
                         "currency": h.get("currency") or "EUR", "avg_price": h.get("avg_price"),
                         "as_of": importer.today()})
        st.replace_holdings(account_id, rows)
        out["holdings"] = len(rows)
        out["assigned"] = wealth.auto_assign(st, account_id, rows)
    st.update_broker_account(account_id, status="ok", last_sync=now_iso(), last_error=None)
    return out
