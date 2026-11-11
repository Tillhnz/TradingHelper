from pathlib import Path

import pytest

from app import learn, news, sentiment
from app.storage import Storage

DATA = Path(__file__).parent / "data"


def _rows(name):
    out = []
    for line in (DATA / name).read_text(encoding="utf-8").splitlines():
        if line[:1] in "-01":
            label, text = line.split("\t", 1)
            out.append((int(label), text))
    return out


def _label(v):
    return 1 if v > 0.15 else -1 if v < -0.15 else 0


@pytest.mark.parametrize("name", ["sentiment_headlines.tsv", "sentiment_holdout.tsv", "sentiment_fresh.tsv"])
def test_accuracy_on_labelled_headlines(name):
    rows = _rows(name)
    wrong = [(y, t) for y, t in rows if _label(sentiment.score(t)) != y]
    assert len(wrong) / len(rows) <= 0.06, wrong
    # Die Richtung darf so gut wie nie kippen (positiv als negativ oder umgekehrt)
    flipped = [(y, t) for y, t in rows if y and _label(sentiment.score(t)) == -y]
    assert len(flipped) <= 1, flipped


def test_cases_from_the_app():
    f = sentiment.score
    assert f("Spionageskandal: Wie stark ein Rücktritt Huangs Nvidia schaden könnte") < -0.15
    assert f("NVIDIA-Aktie nach Huang-Affäre: Drohen jetzt härtere Chip-Exportregeln?") < -0.15
    assert f("Nvidia Aktie: Anleger greifen kräftig zu") > 0.15
    assert f("Bayer Wins Twin Approvals and a Guidance Lift, but Jefferies Stays on the Fence") > 0.15
    assert f("Siemens Energy is targeting a 20% to 22% profit margin by 2030 after a record year") > 0.15
    assert f("SAP keeps promoting its Joule AI tools but still hasn't published numbers to test them") < -0.15


def test_context_rules():
    f = sentiment.score
    assert f("BASF steigert Ergebnis trotz schwacher Konjunktur") > 0.15
    assert f("Despite record sales, Nike cuts outlook") < -0.15
    assert f("Anleger kaufen Tech-Aktien nach Kursrutsch") > 0.15
    assert f("Gericht weist Klage gegen Bayer ab") > 0.15
    assert f("Should You Buy Nvidia Stock Right Now?") == 0
    assert f("Droht der Tesla-Aktie jetzt der Absturz?") < -0.15
    assert f("Kein Grund zur Sorge: Aktie nicht unter Druck") > 0
    assert f("iShares Core MSCI World ETF mit grünen Vorzeichen") > 0.15
    assert f("DAX mit roten Vorzeichen") < -0.15
    assert f("Arbeitslosigkeit steigt auf höchsten Stand seit Jahren") < -0.15


def test_learning_from_corrections(tmp_path):
    st = Storage(tmp_path / "t.db")
    h = "Acme meldet Quartalszahlen – Handelsblatt"
    assert news.score_text(h) == 0
    st.add_news_feedback(h, -1)
    learn.refresh(st)
    assert news.score_text("Acme meldet Quartalszahlen - Finanzen.net") == pytest.approx(-0.6)  # gleiche Meldung, andere Quelle
    # Wörter lernen erst ab zwei Korrekturen
    st.add_news_feedback("Acme Bilanzloch entdeckt", -1)
    st.add_news_feedback("Bilanzloch bei Beta AG", -1)
    learn.refresh(st)
    assert learn.TOKENS.get("bilanzloch", 0) < 0
    assert news.score_text("Neues Bilanzloch bei Gamma") < -0.15
    # Korrektur überschreibt eine frühere zur selben Schlagzeile
    st.add_news_feedback(h, 1)
    learn.refresh(st)
    assert news.score_text(h) == pytest.approx(0.6)
    learn.OVERRIDES, learn.TOKENS = {}, {}
