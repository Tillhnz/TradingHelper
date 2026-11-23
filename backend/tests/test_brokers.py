import sys
import types

import pytest

from app.brokers import fints_sync, importer, valid_isin
from app.storage import Storage


def test_isin_checksum():
    assert valid_isin("US0378331005") and valid_isin("DE0007164600") and valid_isin("IE00B4L5Y983")
    assert not valid_isin("US0378331006") and not valid_isin("DE000716460") and not valid_isin("")


@pytest.mark.parametrize("text,value", [("1.234,56", 1234.56), ("1,234.56", 1234.56), ("-12,5 €", -12.5),
                                        ("10", 10.0), ("0,25", 0.25), ("1.000", 1000.0), ("12.5", 12.5),
                                        ("", None), ("abc", None), ("1 234,50", 1234.5)])
def test_numbers(text, value):
    assert importer.number(text) == value


def test_csv_semicolon_german():
    csv_text = (
        "Datum;Uhrzeit;Typ;Wertpapier;ISIN;Stück;Kurs;Gebühren;Betrag\n"
        "15.03.2026;09:12;Kauf;SAP SE;DE0007164600;10;180,50;1,00;-1.806,00\n"
        "20.03.2026;10:00;Dividende;SAP SE;DE0007164600;;;;22,00\n"
        "02.04.2026;14:33:10;Verkauf;SAP SE;DE0007164600;10;195,00;1,00;1.949,00\n"
    )
    p = importer.parse_csv(csv_text.encode("utf-8"))
    assert p.kind == "trades" and len(p.trades) == 2
    buy, sell = p.trades
    assert (buy.side, buy.quantity, buy.price, buy.day, buy.time, buy.fees) == ("buy", 10, 180.5, "2026-03-15", "09:12", 1.0)
    assert sell.side == "sell" and sell.time == "14:33"
    assert any("Dividende" in s for s in p.skipped)
    assert buy.fingerprint != sell.fingerprint


def test_csv_comma_quoted_english_and_price_from_amount():
    csv_text = ('"Date","Type","ISIN","Name","Quantity","Amount"\n'
                '"2026-05-02","Buy","US0378331005","Apple Inc","2","400.00"\n')
    p = importer.parse_csv(csv_text)
    assert p.trades[0].price == 200.0 and p.trades[0].name == "Apple Inc"


def test_csv_holdings_list():
    csv_text = "ISIN;Bezeichnung;Bestand;Kurs;Wert\nIE00B4L5Y983;iShares Core MSCI World;12,5;95,10;1.188,75\n"
    p = importer.parse_csv(csv_text)
    assert p.kind == "holdings" and p.holdings[0].quantity == 12.5 and p.holdings[0].value == 1188.75


PDF_TEXT = """Baader Bank AG · Weihenstephaner Straße 4 · 85716 Unterschleißheim
Wertpapierabrechnung: Kauf
Nominale ISIN: DE0007164600 WKN: 716460 Kurs
STK 5 SAP SE EUR 183,24
Inhaber-Aktien o.N.
Handelstag 12.06.2026 Kurswert EUR 916,20
Handelszeit 10:41:07 Provision EUR 0,99
Börse: gettex
Zu Lasten Konto 12345 Valuta 16.06.2026 EUR 917,19
"""


def test_pdf_statement_text():
    trades = importer.parse_statement_text(PDF_TEXT)
    assert len(trades) == 1
    t = trades[0]
    assert (t.side, t.isin, t.quantity, t.price, t.day, t.time, t.fees) == ("buy", "DE0007164600", 5, 183.24,
                                                                            "2026-06-12", "10:41", 0.99)


def test_apply_trades_blocks_and_dedupe(tmp_path):
    st = Storage(tmp_path / "x.db")
    uid = st.create_user("till", "x")
    st = st.for_user(uid)
    p = importer.parse_csv(
        "Datum;Typ;ISIN;Stück;Kurs\n"
        "01.02.2026;Kauf;DE0007164600;10;100\n"
        "05.02.2026;Kauf;DE0007164600;4;110\n"
        "01.03.2026;Verkauf;DE0007164600;4;120\n"     # genau ein Block → dieser wird geschlossen
        "01.04.2026;Verkauf;DE0007164600;6;130\n")    # kein passender Block → FIFO mit Teilung
    rows = [t.to_dict() for t in p.trades]
    res = importer.apply_trades(st, rows, None, "Import")
    assert res == {"created": 2, "closed": 2, "duplicates": 0, "problems": []}
    pos = st.positions("DE0007164600.GTX")
    open_ = [x for x in pos if not x["sell_date"]]
    closed = [x for x in pos if x["sell_date"]]
    assert len(open_) == 1 and open_[0]["quantity"] == 4 and open_[0]["buy_price"] == 100
    assert sorted((x["quantity"], x["buy_price"], x["sell_price"]) for x in closed) == [(4, 110, 120), (6, 100, 130)]
    again = importer.apply_trades(st, rows, None, "Import")
    assert again["duplicates"] == 4 and again["created"] == 0


# ---------- FinTS mit einer nachgebauten Bank ----------

class _NeedTAN:
    def __init__(self, label, decoupled=False):
        self.challenge, self.decoupled, self.label = f"Bitte {label} freigeben", decoupled, label
        self.challenge_matrix = ("image/png", b"PNG") if not decoupled else None

    def get_data(self):
        return self.label.encode()


class _Retry:
    @staticmethod
    def from_data(blob):
        return _NeedTAN(blob.decode())


class _Holding:
    def __init__(self, isin, pieces, price):
        self.ISIN, self.name, self.pieces, self.market_value = isin, "Wert " + isin, pieces, price
        self.total_value, self.value_symbol, self.valuation_date, self.acquisitionprice = pieces * price, "EUR", None, None


class _Account:
    def __init__(self, **kw):
        self.__dict__.update(kw)


BANK = {"tan_on_init": True, "tan_on_holdings": True, "confirmed": set()}


class _Client:
    def __init__(self, blz, login, pin, url, customer_id=None, product_id=None, from_data=None):
        assert product_id == "PID"
        self.pin, self.init_tan_response, self.data = pin, None, from_data

    def get_current_tan_mechanism(self):
        return "900"

    def is_tan_media_required(self):
        return False

    def __enter__(self):
        if BANK["tan_on_init"] and "init" not in BANK["confirmed"]:
            self.init_tan_response = _NeedTAN("init", decoupled=True)
        return self

    def __exit__(self, *a):
        return False

    def pause_dialog(self):
        return b"dialog"

    def deconstruct(self, including_private=False):
        return b"client-state"

    def resume_dialog(self, data):
        assert data == b"dialog"
        return self

    def send_tan(self, resp, tan):
        if resp.label == "init":
            BANK["confirmed"].add("init")
            return None
        if resp.label == "holdings":
            assert tan == "123456"
            BANK["confirmed"].add("holdings")
            return [_Holding("DE0007164600", 5, 180.0)]
        raise AssertionError(resp.label)

    def get_sepa_accounts(self):
        return [_Account(iban="DE1", bic="X", accountnumber="111", subaccount=None, blz="760"),
                _Account(iban="DE2", bic="X", accountnumber="222", subaccount=None, blz="760")]

    def get_holdings(self, acc):
        if acc.accountnumber == "111":
            raise RuntimeError("kein Depot")
        if BANK["tan_on_holdings"] and "holdings" not in BANK["confirmed"]:
            return _NeedTAN("holdings")
        return [_Holding("DE0007164600", 5, 180.0)]


@pytest.fixture
def fake_fints(monkeypatch):
    client_mod = types.SimpleNamespace(FinTS3PinTanClient=_Client, NeedTANResponse=_NeedTAN, NeedRetryResponse=_Retry)
    models_mod = types.SimpleNamespace(SEPAAccount=_Account)
    pkg = types.ModuleType("fints")
    pkg.client, pkg.models = client_mod, models_mod
    monkeypatch.setitem(sys.modules, "fints", pkg)
    monkeypatch.setitem(sys.modules, "fints.client", client_mod)
    monkeypatch.setitem(sys.modules, "fints.models", models_mod)
    BANK.update(tan_on_init=True, tan_on_holdings=True, confirmed=set())


def test_fints_flow_with_two_approvals(fake_fints):
    account = {"id": 7, "config": {"blz": "76030080", "login": "123", "url": "https://bank"}}
    r = fints_sync.start(account, "1234", "PID", None, user_id=1)
    assert not r.done and r.challenge["decoupled"] is True and r.session
    r = fints_sync.resume(r.session, "", "PID", account, user_id=1)  # App-Freigabe bestätigt
    assert not r.done and r.challenge["image"].startswith("data:image/png;base64,")  # photoTAN für die Depotabfrage
    with pytest.raises(fints_sync.BrokerError):
        fints_sync.resume("falsch", "1", "PID", account, user_id=1)
    r2 = fints_sync.resume(r.session, "123456", "PID", account, user_id=1)
    assert r2.done and r2.accounts == 2 and r2.client_data == b"client-state"
    h = r2.holdings[0]
    assert h["symbol"] == "DE0007164600.GTX" and h["quantity"] == 5 and h["value"] == 900 and h["depot"] == "222"


def test_fints_no_tan_needed(fake_fints):
    BANK.update(tan_on_init=False, tan_on_holdings=False)
    account = {"id": 1, "config": {"blz": "1", "login": "1", "url": "u"}}
    r = fints_sync.start(account, "1", "PID", b"old", user_id=1)
    assert r.done and len(r.holdings) == 1


def test_fints_requires_product_id(fake_fints):
    with pytest.raises(fints_sync.BrokerError, match="Produkt-Registrierungsnummer"):
        fints_sync.start({"id": 1, "config": {"blz": "1", "login": "1", "url": "u"}}, "1", "", None, user_id=1)


def test_seal_roundtrip():
    tok = fints_sync.seal("k", "1234", b"\x00state")
    assert "1234" not in tok
    assert fints_sync.unseal("k", tok) == ("1234", b"\x00state")
    assert fints_sync.unseal("anders", tok) == ("", None)
