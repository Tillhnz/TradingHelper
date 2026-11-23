"""Depotbestand per FinTS (HBCI PIN/TAN) abrufen – nur lesend.

Ablauf in der Oberfläche:
1. Zugang anlegen (Bank, Anmeldename, PIN; PIN optional gespeichert, verschlüsselt).
2. „Abrufen“ → die Bank verlangt seit PSD2 meist eine Freigabe (TAN). Dann pausiert TradeHelper den Dialog und zeigt
   die Aufforderung bzw. die photoTAN-Grafik. Bei App-Freigaben (decoupled) reicht „In der App bestätigt“.
3. Mit der Freigabe geht es weiter: Kontenliste → Depotaufstellung je Depot → Bestände werden gespeichert.
Die Sitzungsdaten der Bank (System-ID, Bankparameter) bleiben verschlüsselt gespeichert, damit die Bank das Gerät
wiedererkennt und nur etwa alle 90 Tage eine neue Freigabe verlangt.

Für FinTS braucht jede Software eine (kostenlose) Produkt-Registrierungsnummer der Deutschen Kreditwirtschaft:
https://www.hbci-zka.de/register/prod_register.htm → in TradeHelper unter Administration → Broker eintragen.
"""

from __future__ import annotations

import base64
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import date

from .. import crypto
from . import BrokerError, valid_isin

log = logging.getLogger(__name__)

SESSION_TTL = 600
_SESSIONS: dict[str, "Pending"] = {}
_LOCK = threading.Lock()
PURPOSE_PIN = "fints-pin"
PURPOSE_CLIENT = "fints-client"


@dataclass
class Pending:
    """Pausierter Dialog, der auf eine TAN wartet."""
    account_id: int
    user_id: int
    pin: str
    client_data: bytes
    dialog_data: bytes
    tan_data: bytes
    stage: str                     # "init" | "accounts" | "holdings"
    accounts: list[dict] = field(default_factory=list)
    index: int = 0
    collected: list[dict] = field(default_factory=list)
    created: float = field(default_factory=time.time)


def _fints():
    try:
        from fints import client as fc
        from fints import models as fm
    except ImportError as exc:  # pragma: no cover - im Container installiert
        raise BrokerError("Die Bibliothek python-fints fehlt (requirements.txt).") from exc
    return fc, fm


def _prune() -> None:
    now = time.time()
    with _LOCK:
        for k in [k for k, v in _SESSIONS.items() if now - v.created > SESSION_TTL]:
            _SESSIONS.pop(k, None)


def _client(cfg: dict, pin: str, product_id: str, client_data: bytes | None):
    fc, _ = _fints()
    if not product_id:
        raise BrokerError("Für FinTS fehlt die Produkt-Registrierungsnummer (Administration → Broker). Sie ist "
                          "kostenlos bei der Deutschen Kreditwirtschaft erhältlich.")
    return fc.FinTS3PinTanClient(cfg["blz"], cfg["login"], pin, cfg["url"], customer_id=cfg.get("customer_id") or None,
                                 product_id=product_id, from_data=client_data or None)


def _pick_mechanism(client, wanted: str | None) -> None:
    """TAN-Verfahren wählen: das gespeicherte, sonst bevorzugt eine App-Freigabe (decoupled), sonst das erste."""
    try:
        if not client.get_current_tan_mechanism() or wanted:
            client.fetch_tan_mechanisms()
            mechs = client.get_tan_mechanisms() or {}
            if mechs:
                if wanted and wanted in mechs:
                    client.set_tan_mechanism(wanted)
                elif not client.get_current_tan_mechanism():
                    def rank(item):
                        name = (getattr(item[1], "name", "") or "").lower()
                        return 0 if any(w in name for w in ("app", "push", "decoupled", "secure")) else 1
                    client.set_tan_mechanism(sorted(mechs.items(), key=rank)[0][0])
        if client.is_tan_media_required() and not client.selected_tan_medium:
            media = client.get_tan_media()
            if media and media[1]:
                client.set_tan_medium(media[1][0])
    except Exception as exc:  # noqa: BLE001 – manche Banken melden das nicht; der Dialog klärt es dann selbst
        log.info("TAN-Verfahren nicht ermittelbar: %s", exc)


def mechanisms(cfg: dict, pin: str, product_id: str, client_data: bytes | None) -> list[dict]:
    client = _client(cfg, pin, product_id, client_data)
    client.fetch_tan_mechanisms()
    return [{"id": k, "name": getattr(v, "name", str(k))} for k, v in (client.get_tan_mechanisms() or {}).items()]


def _challenge(resp) -> dict:
    out = {"text": (getattr(resp, "challenge", None) or "Bitte die Anmeldung bei deiner Bank freigeben.").strip(),
           "decoupled": bool(getattr(resp, "decoupled", False)), "image": None, "flicker": None}
    html = getattr(resp, "challenge_html", None)
    if html:
        out["html"] = str(html)
    matrix = getattr(resp, "challenge_matrix", None)  # photoTAN: (MIME-Typ, Bilddaten)
    if matrix:
        try:
            mime, data = matrix
            out["image"] = f"data:{mime};base64,{base64.b64encode(data).decode()}"
        except (TypeError, ValueError):
            pass
    hhd = getattr(resp, "challenge_hhduc", None)
    if hhd:
        out["flicker"] = str(hhd)
    return out


def _holding_dict(h) -> dict | None:
    isin = (getattr(h, "ISIN", None) or "").strip().upper()
    qty = getattr(h, "pieces", None)
    if qty is None:
        return None
    price = getattr(h, "market_value", None)
    total = getattr(h, "total_value", None)
    vd = getattr(h, "valuation_date", None)
    return {
        "isin": isin if valid_isin(isin) else (isin or None),
        "symbol": f"{isin}.GTX" if valid_isin(isin) else None,
        "name": (getattr(h, "name", None) or "").strip() or isin,
        "quantity": float(qty),
        "price": float(price) if price is not None else None,
        "value": float(total) if total is not None else (float(price) * float(qty) if price is not None else None),
        "currency": getattr(h, "value_symbol", None) or "EUR",
        "avg_price": float(getattr(h, "acquisitionprice", None)) if getattr(h, "acquisitionprice", None) else None,
        "as_of": vd.isoformat() if isinstance(vd, date) else (str(vd) if vd else None),
    }


def _acc_dict(a) -> dict:
    return {k: getattr(a, k, None) for k in ("iban", "bic", "accountnumber", "subaccount", "blz")}


class Result:
    """Ergebnis eines Schritts: entweder fertig (holdings) oder Freigabe nötig (challenge + session)."""

    def __init__(self, holdings: list[dict] | None = None, challenge: dict | None = None, session: str | None = None,
                 client_data: bytes | None = None, accounts: int = 0):
        self.holdings, self.challenge, self.session = holdings, challenge, session
        self.client_data, self.accounts = client_data, accounts

    @property
    def done(self) -> bool:
        return self.holdings is not None


def _pause(client, resp, p: Pending) -> Result:
    p.tan_data = resp.get_data()
    p.dialog_data = client.pause_dialog()
    return Result(challenge=_challenge(resp), session=_store(p))


def _store(p: Pending) -> str:
    _prune()
    sid = secrets.token_urlsafe(18)
    with _LOCK:
        _SESSIONS[sid] = p
    return sid


def _run(client, p: Pending, fc, fm, resumed_result=None) -> Result:
    """Läuft innerhalb eines offenen (oder fortgesetzten) Dialogs weiter, bis alles da ist oder eine TAN fehlt."""
    res = resumed_result
    if p.stage == "init":
        p.stage = "accounts"
        res = None
    if p.stage == "accounts":
        if res is None:
            res = client.get_sepa_accounts()
        if isinstance(res, fc.NeedTANResponse):
            return _pause(client, res, p)
        p.accounts = [_acc_dict(a) for a in (res or [])]
        p.stage, p.index, res = "holdings", 0, None
    while p.index < len(p.accounts):
        acc = fm.SEPAAccount(**p.accounts[p.index])
        if res is None:
            try:
                res = client.get_holdings(acc)
            except Exception as exc:  # noqa: BLE001 – Girokonten kennen keine Depotaufstellung
                log.info("Keine Depotaufstellung für %s: %s", p.accounts[p.index].get("accountnumber"), exc)
                res = []
        if isinstance(res, fc.NeedTANResponse):
            return _pause(client, res, p)
        for h in res or []:
            d = _holding_dict(h)
            if d:
                d["depot"] = p.accounts[p.index].get("accountnumber")
                p.collected.append(d)
        p.index += 1
        res = None
    return Result(holdings=p.collected, accounts=len(p.accounts))


def _finish(client, result: Result) -> Result:
    """Nach dem Dialog (beendet oder pausiert): Sitzungsdaten sichern – bei Pause für die Fortsetzung, sonst für den
    nächsten Abruf (die Bank erkennt TradeHelper daran wieder)."""
    data = client.deconstruct(including_private=True)
    if result.done:
        result.client_data = data
    else:
        with _LOCK:
            if result.session in _SESSIONS:
                _SESSIONS[result.session].client_data = data
    return result


def start(account: dict, pin: str, product_id: str, client_data: bytes | None, user_id: int) -> Result:
    fc, fm = _fints()
    cfg = account["config"]
    client = _client(cfg, pin, product_id, client_data)
    _pick_mechanism(client, cfg.get("tan_mechanism"))
    p = Pending(account["id"], user_id, pin, b"", b"", b"", "init")
    with client:
        init = client.init_tan_response
        if isinstance(init, fc.NeedTANResponse):
            result = _pause(client, init, p)
        else:
            result = _run(client, p, fc, fm)
    return _finish(client, result)


def resume(session_id: str, tan: str, product_id: str, account: dict, user_id: int) -> Result:
    fc, fm = _fints()
    with _LOCK:
        p = _SESSIONS.pop(session_id, None)
    if not p or p.user_id != user_id or p.account_id != account["id"]:
        raise BrokerError("Die Freigabe ist abgelaufen. Bitte noch einmal abrufen.")
    client = _client(account["config"], p.pin, product_id, p.client_data)
    with client.resume_dialog(p.dialog_data):
        res = client.send_tan(fc.NeedRetryResponse.from_data(p.tan_data), tan or "")
        if isinstance(res, fc.NeedTANResponse):  # App-Freigabe noch nicht bestätigt oder weitere TAN nötig
            result = _pause(client, res, p)
        else:
            result = _run(client, p, fc, fm, resumed_result=None if p.stage == "init" else res)
    return _finish(client, result)


def cancel(session_id: str) -> None:
    with _LOCK:
        _SESSIONS.pop(session_id, None)


# ---------- Geheimnisse ----------

def seal(secret_key: str, pin: str | None, client_data: bytes | None) -> str:
    import json

    return crypto.encrypt(json.dumps({
        "pin": pin or "",
        "client": base64.b64encode(client_data).decode() if client_data else "",
    }), secret_key, PURPOSE_CLIENT)


def unseal(secret_key: str, token: str) -> tuple[str, bytes | None]:
    import json

    if not token:
        return "", None
    try:
        data = json.loads(crypto.decrypt(token, secret_key, PURPOSE_CLIENT))
    except (crypto.CryptoError, ValueError):
        return "", None
    client = base64.b64decode(data["client"]) if data.get("client") else None
    return data.get("pin") or "", client
