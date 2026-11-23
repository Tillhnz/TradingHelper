"""Gesamtportfolio und Depot-Verbindungen (nur lesend)."""

from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import notify, wealth
from .brokers import BANKS, BrokerError, fints_sync, importer
from .config import Settings
from .config import settings as base_settings
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
    return {"banks": [{"id": k, **v} for k, v in BANKS.items()],
            "fints_ready": bool(base_settings.fints_product_id)}


class AccountIn(BaseModel):
    bank: str = Field(min_length=2, max_length=30)
    label: str = Field(default="", max_length=60)
    blz: str = Field(default="", max_length=12)
    login: str = Field(default="", max_length=60)
    customer_id: str = Field(default="", max_length=60)
    url: str = Field(default="", max_length=200)
    pin: str = Field(default="", max_length=80)
    save_pin: bool = False


def _account_or_404(st: Storage, account_id: int) -> dict:
    a = st.broker_account(account_id)
    if not a:
        raise HTTPException(404, "Depot-Verbindung nicht gefunden")
    return a


@router.post("/api/portfolio/accounts", status_code=201)
def account_add(item: AccountIn, st: Storage = Depends(user_storage)):
    bank = BANKS.get(item.bank)
    if not bank:
        raise HTTPException(422, "Unbekannte Bank")
    config: dict = {}
    if bank["kind"] == "fints":
        blz = (item.blz or bank.get("blz") or "").replace(" ", "")
        url = item.url or bank.get("url") or ""
        if not blz.isdigit() or len(blz) != 8:
            raise HTTPException(422, "Bitte die 8-stellige Bankleitzahl angeben.")
        if not url.startswith("https://"):
            raise HTTPException(422, "Bitte die FinTS-Adresse der Bank angeben (https://…).")
        if not item.login.strip():
            raise HTTPException(422, f"Bitte {bank['login_label']} angeben.")
        config = {"blz": blz, "url": url, "login": item.login.strip(), "customer_id": item.customer_id.strip(),
                  "save_pin": item.save_pin}
    secret = fints_sync.seal(base_settings.secret_key, item.pin if item.save_pin else "", None) if bank["kind"] == "fints" else ""
    aid = st.add_broker_account(bank["kind"], item.bank, item.label.strip() or bank["name"], config, secret)
    return {"id": aid}


class AccountPatch(BaseModel):
    label: str | None = Field(default=None, max_length=60)
    pin: str | None = Field(default=None, max_length=80)
    save_pin: bool | None = None
    tan_mechanism: str | None = Field(default=None, max_length=10)


@router.patch("/api/portfolio/accounts/{account_id}")
def account_patch(account_id: int, item: AccountPatch, st: Storage = Depends(user_storage)):
    a = _account_or_404(st, account_id)
    fields: dict = {}
    if item.label is not None:
        fields["label"] = item.label.strip() or BANKS.get(a["bank"], {}).get("name", a["bank"])
    cfg = dict(a["config"])
    if item.tan_mechanism is not None:
        cfg["tan_mechanism"] = item.tan_mechanism or None
    if a["kind"] == "fints" and (item.save_pin is not None or item.pin is not None):
        pin, client = fints_sync.unseal(base_settings.secret_key, a["secret"])
        save = cfg.get("save_pin", False) if item.save_pin is None else item.save_pin
        if item.pin is not None:
            pin = item.pin
        cfg["save_pin"] = save
        fields["secret"] = fints_sync.seal(base_settings.secret_key, pin if save else "", client)
    fields["config"] = cfg
    st.update_broker_account(account_id, **fields)
    return {"ok": True}


@router.delete("/api/portfolio/accounts/{account_id}")
def account_delete(account_id: int, st: Storage = Depends(user_storage)):
    """Verbindung und abgerufene Bestände löschen. Importierte Käufe bleiben im Depot (ohne Zuordnung)."""
    if not st.delete_broker_account(account_id):
        raise HTTPException(404, "Depot-Verbindung nicht gefunden")
    return {"ok": True}


# ---------- FinTS ----------

class SyncIn(BaseModel):
    pin: str = Field(default="", max_length=80)


class TanIn(BaseModel):
    session: str = Field(min_length=8, max_length=80)
    tan: str = Field(default="", max_length=40)


def _sync_result(st: Storage, a: dict, r: fints_sync.Result, pin: str) -> dict:
    if not r.done:
        st.update_broker_account(a["id"], status="tan", last_error=None)
        return {"status": "tan", "session": r.session, "challenge": r.challenge}
    st.replace_holdings(a["id"], r.holdings)
    assigned = wealth.auto_assign(st, a["id"], r.holdings)
    keep_pin = pin if a["config"].get("save_pin") else ""
    st.update_broker_account(a["id"], status="ok", last_sync=now_iso(), last_error=None,
                             secret=fints_sync.seal(base_settings.secret_key, keep_pin, r.client_data))
    return {"status": "ok", "holdings": len(r.holdings), "accounts": r.accounts, "assigned": assigned}


def _fints_error(st: Storage, a: dict, exc: Exception) -> HTTPException:
    msg = str(exc) or type(exc).__name__
    name = type(exc).__name__
    if "PIN" in name or "pin" in msg.lower():
        msg = "Die Bank hat die Anmeldung abgelehnt (PIN oder Anmeldename prüfen). Nach mehreren Fehlversuchen " \
              "sperrt die Bank den Zugang."
    st.update_broker_account(a["id"], status="error", last_error=msg[:300])
    log.warning("FinTS-Abruf %s fehlgeschlagen: %s: %s", a["bank"], name, exc)
    return HTTPException(502, msg[:300])


@router.post("/api/portfolio/accounts/{account_id}/sync")
def account_sync(account_id: int, item: SyncIn, st: Storage = Depends(user_storage)):
    a = _account_or_404(st, account_id)
    if a["kind"] != "fints":
        raise HTTPException(409, "Dieses Depot wird per Import aktualisiert.")
    saved_pin, client = fints_sync.unseal(base_settings.secret_key, a["secret"])
    pin = item.pin or saved_pin
    if not pin:
        raise HTTPException(422, "Bitte die PIN eingeben (oder in der Verbindung speichern).")
    try:
        r = fints_sync.start(a, pin, base_settings.fints_product_id, client, st.uid)
    except BrokerError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise _fints_error(st, a, exc) from exc
    return _sync_result(st, a, r, pin)


@router.post("/api/portfolio/accounts/{account_id}/tan")
def account_tan(account_id: int, item: TanIn, st: Storage = Depends(user_storage)):
    a = _account_or_404(st, account_id)
    try:
        pending = fints_sync._SESSIONS.get(item.session)
        pin = pending.pin if pending else ""
        r = fints_sync.resume(item.session, item.tan.strip(), base_settings.fints_product_id, a, st.uid)
    except BrokerError as exc:
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise _fints_error(st, a, exc) from exc
    return _sync_result(st, a, r, pin)


@router.delete("/api/portfolio/tan/{session}")
def tan_cancel(session: str):
    fints_sync.cancel(session)
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


# ---------- Hintergrund: Bankdepots mit gespeicherter PIN regelmäßig abrufen ----------

def background_sync(storage: Storage, settings: Settings) -> int:
    """Für den Scheduler. Verlangt die Bank eine Freigabe, gibt es eine Push-Nachricht statt zu warten."""
    if not base_settings.fints_product_id:
        return 0
    n = 0
    for a in storage.broker_accounts():
        if a["kind"] != "fints" or not a["config"].get("save_pin"):
            continue
        pin, client = fints_sync.unseal(base_settings.secret_key, a["secret"])
        if not pin:
            continue
        try:
            r = fints_sync.start(a, pin, base_settings.fints_product_id, client, storage.uid)
        except Exception as exc:  # noqa: BLE001
            storage.update_broker_account(a["id"], status="error", last_error=str(exc)[:300])
            continue
        if r.done:
            _sync_result(storage, a, r, pin)
            n += 1
        else:
            fints_sync.cancel(r.session)
            if a["status"] != "tan_needed":
                notify.send(settings, f"{a['label']}: Freigabe nötig",
                            "Deine Bank möchte den Depotabruf neu freigeben. In TradeHelper unter Portfolio → "
                            "„Abrufen“ antippen.", tags=["key"], path="/portfolio")
            storage.update_broker_account(a["id"], status="tan_needed")
    return n
