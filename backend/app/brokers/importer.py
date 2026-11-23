"""Import von Käufen und Verkäufen aus CSV-Umsatzlisten und PDF-Abrechnungen (z. B. finanzen.net zero / Baader Bank).

Erkannt wird tolerant: Trennzeichen (; , Tab |), deutsche und englische Zahlen („1.234,56“ / „1,234.56“), Datumsformate,
Spaltennamen in Deutsch und Englisch. Eine CSV ohne Kauf/Verkauf-Spalte, aber mit ISIN und Stückzahl, gilt als
Bestandsliste (Depotaufstellung).

Jede erkannte Zeile bekommt einen Fingerabdruck – mehrfach hochgeladene Dateien legen nichts doppelt an.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime

from . import valid_isin

BUY, SELL = "buy", "sell"


@dataclass
class Trade:
    side: str
    isin: str
    quantity: float
    price: float
    day: str
    time: str | None = None
    fees: float = 0.0
    name: str | None = None
    currency: str = "EUR"
    source: str = ""

    @property
    def fingerprint(self) -> str:
        raw = f"{self.side}|{self.isin}|{self.day}|{self.time or ''}|{self.quantity:.6f}|{self.price:.4f}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def to_dict(self) -> dict:
        return {**asdict(self), "fingerprint": self.fingerprint, "symbol": f"{self.isin}.GTX"}


@dataclass
class Holding:
    isin: str
    quantity: float
    name: str | None = None
    price: float | None = None
    value: float | None = None
    avg_price: float | None = None
    currency: str = "EUR"

    def to_dict(self) -> dict:
        return {**asdict(self), "symbol": f"{self.isin}.GTX"}


@dataclass
class Parsed:
    trades: list[Trade]
    holdings: list[Holding]
    skipped: list[str]
    kind: str  # "trades" | "holdings" | "empty"
    format: str

    def to_dict(self) -> dict:
        return {"kind": self.kind, "format": self.format, "trades": [t.to_dict() for t in self.trades],
                "holdings": [h.to_dict() for h in self.holdings], "skipped": self.skipped[:50]}


# ---------- Zahlen und Daten ----------

def number(text, decimal: str | None = None) -> float | None:
    """„1.234,56“, „1,234.56“, „-12,5 €“, „1 234,5“ → float. decimal="." oder "," löst Fälle wie „1.000“ auf
    (ohne Angabe: deutsch, also Tausenderpunkt)."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip().replace(" ", " ").replace("€", "").replace("EUR", "").replace("USD", "").strip()
    s = s.replace(" ", "").replace("'", "")
    neg = s.startswith("-") or s.endswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("-+()")
    if not s or not re.fullmatch(r"[\d.,]+", s):
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):  # deutsch: 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:  # englisch: 1,234.56
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        s = s.replace(",", ".") if len(parts) == 2 else s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif s.count(".") == 1 and decimal != "." and re.fullmatch(r"\d{1,3}\.\d{3}", s):
        s = s.replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def parse_day(text) -> str | None:
    s = str(text or "").strip()
    for pat, fmt in ((r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"), (r"\d{2}\.\d{2}\.\d{4}", "%d.%m.%Y"),
                     (r"\d{2}\.\d{2}\.\d{2}(?!\d)", "%d.%m.%y"), (r"\d{2}/\d{2}/\d{4}", "%d/%m/%Y")):
        m = re.search(pat, s)
        if m:
            try:
                return datetime.strptime(m.group(0), fmt).date().isoformat()
            except ValueError:
                continue
    return None


def parse_time(text) -> str | None:
    m = re.search(r"\b([01]\d|2[0-3]):([0-5]\d)", str(text or ""))
    return f"{m.group(1)}:{m.group(2)}" if m else None


def side_of(text) -> str | None:
    t = _norm(str(text or ""))
    if not t:
        return None
    if any(w in t for w in ("verkauf", "sell", "abgang", "veraeusserung")):
        return SELL
    if any(w in t for w in ("kauf", "buy", "zugang", "sparplan", "erwerb", "purchase")):
        return BUY
    return None


def _norm(s: str) -> str:
    s = s.lower().strip().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9/]+", " ", s).strip()


# ---------- CSV ----------

COLUMNS = {
    "isin": ["isin", "wkn/isin", "isin/wkn", "wertpapierkennnummer isin"],
    "name": ["name", "wertpapier", "bezeichnung", "titel", "produkt", "instrument", "wertpapiername", "security"],
    "side": ["typ", "art", "transaktion", "transaktionsart", "buchungsart", "richtung", "kauf/verkauf", "side", "type",
             "auftragsart", "geschaeftsart", "order typ", "ordertyp", "vorgang"],
    "quantity": ["stueck", "anzahl", "menge", "nominale", "quantity", "shares", "stueckzahl", "anteile", "stk", "bestand",
                 "nominal"],
    "price": ["kurs", "preis", "ausfuehrungskurs", "price", "kurs in eur", "einstandskurs", "durchschnittskurs",
              "kaufkurs", "ausfuehrungspreis"],
    "amount": ["betrag", "kurswert", "gesamt", "amount", "wert", "gesamtbetrag", "endbetrag", "marktwert", "value",
               "summe"],
    "fees": ["gebuehren", "gebuehr", "provision", "fees", "entgelt", "kosten", "ordergebuehr", "spesen"],
    "date": ["datum", "handelstag", "ausfuehrungsdatum", "valuta", "buchungstag", "date", "schlusstag", "handelsdatum",
             "ausfuehrung", "buchungsdatum", "ausfuehrungszeitpunkt"],
    "time": ["uhrzeit", "zeit", "time", "handelszeit", "ausfuehrungszeit"],
    "currency": ["waehrung", "currency", "whg"],
}


def _sniff(text: str) -> csv.Dialect | type[csv.Dialect]:
    sample = text[:5000]
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t|")
    except csv.Error:
        return csv.excel if sample.count(",") > sample.count(";") else _Semicolon


class _Semicolon(csv.excel):
    delimiter = ";"


def _map_header(header: list[str]) -> dict[str, int]:
    norm = [_norm(h) for h in header]
    out: dict[str, int] = {}
    for key, names in COLUMNS.items():
        for i, h in enumerate(norm):
            if i in out.values():
                continue
            if h in names or any(h.startswith(n + " ") for n in names):
                out[key] = i
                break
    return out


def parse_csv(content: bytes | str, source: str = "csv") -> Parsed:
    text = content.decode("utf-8-sig", errors="replace") if isinstance(content, bytes) else content
    if "�" in text and isinstance(content, bytes):
        text = content.decode("cp1252", errors="replace")
    rows = list(csv.reader(io.StringIO(text), _sniff(text)))
    rows = [r for r in rows if any(c.strip() for c in r)]
    # Kopfzeile: die erste Zeile, in der eine ISIN-, Stück- oder Datums-Spalte erkennbar ist
    head_i, cols = None, {}
    for i, r in enumerate(rows[:15]):
        m = _map_header(r)
        if "isin" in m and ("quantity" in m or "amount" in m):
            head_i, cols = i, m
            break
    skipped: list[str] = []
    if head_i is None:
        return Parsed([], [], ["Keine Spalten für ISIN und Stückzahl gefunden"], "empty", source)
    trades, holdings = [], []
    has_side = "side" in cols
    body = "\n".join(";".join(r) for r in rows[head_i + 1:head_i + 200])
    dec = "," if len(re.findall(r"\d,\d{1,2}\b", body)) >= len(re.findall(r"\d\.\d{1,2}\b", body)) else "."

    def number(text, _dec=dec):
        return globals()["number"](text, _dec)

    for r in rows[head_i + 1:]:
        def col(k, r=r):
            i = cols.get(k)
            return r[i].strip() if i is not None and i < len(r) else ""

        isin = re.sub(r"\s", "", col("isin")).upper()
        isin_m = re.search(r"[A-Z]{2}[A-Z0-9]{9}\d", isin)
        isin = isin_m.group(0) if isin_m else isin
        line = ";".join(r)[:120]
        if not valid_isin(isin):
            skipped.append(f"keine gültige ISIN: {line}")
            continue
        qty = number(col("quantity"))
        price, amount = number(col("price")), number(col("amount"))
        if not has_side:
            if qty is None or qty == 0:
                skipped.append(f"ohne Stückzahl: {line}")
                continue
            holdings.append(Holding(isin, abs(qty), col("name") or None, price,
                                    abs(amount) if amount is not None else None,
                                    price, col("currency") or "EUR"))
            continue
        side = side_of(col("side"))
        if side is None:
            skipped.append(f"weder Kauf noch Verkauf ({col('side') or '–'}): {line}")
            continue
        day = parse_day(col("date"))
        if qty is None or qty == 0 or not day:
            skipped.append(f"Stückzahl oder Datum fehlt: {line}")
            continue
        qty = abs(qty)
        fees = abs(number(col("fees")) or 0.0)
        if price is None and amount:
            price = abs(amount) / qty
        if not price:
            skipped.append(f"ohne Kurs: {line}")
            continue
        trades.append(Trade(side, isin, qty, round(abs(price), 6), day, parse_time(col("time") or col("date")),
                            round(fees, 2), col("name") or None, (col("currency") or "EUR").upper()[:3], source))
    kind = "trades" if trades else "holdings" if holdings else "empty"
    return Parsed(trades, holdings, skipped, kind, source)


# ---------- PDF-Abrechnungen ----------

_ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}\d)\b")
_NUM = r"(-?\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?|-?\d+(?:,\d+)?|-?\d{1,3}(?:,\d{3})*(?:\.\d+)?)"
_FEE_WORDS = r"(?:Provision|Ordergeb(?:ü|ue)hr|Fremdkostenzuschlag|Transaktionsentgelt|B(?:ö|oe)rsengeb(?:ü|ue)hr|" \
             r"Handelsplatzentgelt|Fremde Spesen|Maklercourtage|Abwicklungsentgelt|Orderentgelt|Courtage)"


def pdf_text(content: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _first(pattern: str, text: str, flags=re.I) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1) if m else None


def parse_statement_text(text: str, source: str = "pdf") -> list[Trade]:
    """Eine oder mehrere Wertpapierabrechnungen (Kauf/Verkauf) aus dem Text einer PDF."""
    t = text.replace(" ", " ")
    # mehrere Abrechnungen in einer Datei: an „Wertpapierabrechnung“ bzw. „Abrechnung“ trennen
    parts = re.split(r"(?=Wertpapier-?\s*[Aa]brechnung|Wertpapierabrechnung|Abrechnung\s*(?:Kauf|Verkauf))", t)
    parts = [p for p in parts if _ISIN_RE.search(p)] or [t]
    out = []
    for part in parts:
        side = side_of(_first(r"(?:Wertpapier-?\s*abrechnung|Abrechnung|Geschäftsart|Auftrag)[:\s]*"
                              r"(Kauf|Verkauf|Buy|Sell)", part) or _first(r"\b(Kauf|Verkauf)\b", part))
        isin = next((m for m in _ISIN_RE.findall(part) if valid_isin(m)), None)
        if not side or not isin:
            continue
        qty = number(_first(r"(?:STK|Stück|Stk\.?|St\.)\s*" + _NUM, part) or
                     _first(_NUM + r"\s*(?:STK|Stück|Stk\.?)\b", part))
        price = number(_first(r"(?:Ausf(?:ü|ue)hrungskurs|Kurs|Preis)\s*(?:EUR|USD)?\s*:?\s*" + _NUM, part))
        total = number(_first(r"Kurswert\s*(?:EUR|USD)?\s*:?\s*" + _NUM, part))
        day = parse_day(_first(r"(?:Handelstag|Schlusstag|Ausf(?:ü|ue)hrungstag|Handelsdatum|Ausf(?:ü|ue)hrung|"
                               r"Datum)[^\d]{0,25}(\d{2}\.\d{2}\.\d{4})", part) or "") or parse_day(part)
        tm = parse_time(_first(r"(?:Handelszeit|Ausf(?:ü|ue)hrungszeit|Uhrzeit|Zeit)[^\d]{0,15}(\d{2}:\d{2})", part) or "")
        fees = 0.0
        for m in re.finditer(_FEE_WORDS + r"[^\d\n-]{0,25}" + _NUM, part, re.I):
            v = number(m.group(1))
            if v is not None:
                fees += abs(v)
        if not qty or not day:
            continue
        if not price and total:
            price = total / qty
        if not price:
            continue
        name = _first(r"(?:Wertpapier|Bezeichnung|Gattungsbezeichnung)[:\s]+([^\n]{3,60})", part)
        out.append(Trade(side, isin, abs(qty), round(abs(price), 6), day, tm, round(fees, 2),
                         name.strip() if name else None, "EUR", source))
    return out


def parse_pdf(content: bytes, source: str = "pdf") -> Parsed:
    try:
        text = pdf_text(content)
    except Exception as exc:  # noqa: BLE001
        return Parsed([], [], [f"PDF nicht lesbar: {exc}"], "empty", source)
    trades = parse_statement_text(text, source)
    skipped = [] if trades else ["In dieser PDF wurde keine Kauf- oder Verkaufsabrechnung erkannt."]
    return Parsed(trades, [], skipped, "trades" if trades else "empty", source)


def parse_file(name: str, content: bytes, source: str = "") -> Parsed:
    if content[:5] == b"%PDF-" or name.lower().endswith(".pdf"):
        return parse_pdf(content, source or "pdf")
    return parse_csv(content, source or "csv")


# ---------- Übernahme ins Depot (Blöcke) ----------

def apply_trades(storage, trades: list[dict], account_id: int | None, note: str) -> dict:
    """Käufe werden Blöcke (Positionen). Ein Verkauf schließt bevorzugt einen offenen Block mit genau derselben
    Stückzahl, sonst die ältesten Blöcke (FIFO, ggf. aufgeteilt). Bekannte Fingerabdrücke werden übersprungen."""
    created = closed = dup = 0
    problems: list[str] = []
    for t in sorted(trades, key=lambda x: (x["day"], x.get("time") or "", 0 if x["side"] == BUY else 1)):
        fp = t["fingerprint"]
        if storage.import_seen(fp):
            dup += 1
            continue
        symbol = t.get("symbol") or f"{t['isin']}.GTX"
        if t["side"] == BUY:
            pid = storage.add_position({
                "symbol": symbol, "quantity": float(t["quantity"]), "buy_price": float(t["price"]),
                "buy_date": t["day"], "buy_time": t.get("time"), "fees": float(t.get("fees") or 0),
                "currency": "EUR" if (t.get("currency") or "EUR") == "EUR" else t["currency"],
                "note": note, "account_id": account_id})
            storage.mark_imported(fp, account_id, pid)
            created += 1
            continue
        qty = float(t["quantity"])
        open_ = [p for p in storage.positions(symbol, open_only=True) if p["buy_date"] <= t["day"]]
        exact = next((p for p in open_ if abs(p["quantity"] - qty) < 1e-6), None)
        queue = [exact] if exact else open_
        left = qty
        fee_left = float(t.get("fees") or 0)
        for p in queue:
            if left <= 1e-9:
                break
            take = min(p["quantity"], left)
            fee = round(fee_left * take / qty, 2) if qty else 0
            if take < p["quantity"] - 1e-9:  # Block teilen: Rest bleibt offen
                storage.update_position(p["id"], {"quantity": p["quantity"] - take})
                share = take / p["quantity"]
                storage.add_position({
                    "symbol": symbol, "quantity": take, "buy_price": p["buy_price"], "buy_date": p["buy_date"],
                    "buy_time": p.get("buy_time"), "fees": round((p.get("fees") or 0) * share, 2),
                    "currency": p.get("currency") or "", "stop": p.get("stop"), "target": p.get("target"),
                    "note": p.get("note") or note, "account_id": p.get("account_id"), "sell_price": float(t["price"]),
                    "sell_date": t["day"], "sell_time": t.get("time"), "sell_fees": fee})
                storage.update_position(p["id"], {"fees": round((p.get("fees") or 0) * (1 - share), 2)})
            else:
                storage.update_position(p["id"], {"sell_price": float(t["price"]), "sell_date": t["day"],
                                                  "sell_time": t.get("time"), "sell_fees": fee})
            left -= take
            closed += 1
        if left > 1e-6:
            problems.append(f"Verkauf {t['isin']} am {t['day']}: {left:g} Stück ohne passenden Kauf")
        storage.mark_imported(fp, account_id, None)
    return {"created": created, "closed": closed, "duplicates": dup, "problems": problems}


def today() -> str:
    return date.today().isoformat()
