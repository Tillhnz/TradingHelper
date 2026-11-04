from datetime import datetime, timedelta, timezone

from app import news
from app.config import Settings

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>t</title>
<item><title>SAP hebt Prognose an - Handelsblatt</title><link>https://g/1</link>
<pubDate>Tue, 03 Nov 2026 10:00:00 GMT</pubDate><description>&lt;a href="x"&gt;SAP&lt;/a&gt;</description>
<source url="https://handelsblatt.com">Handelsblatt</source></item>
<item><title>DAX schließt im Plus</title><link>https://g/2</link><pubDate>Tue, 03 Nov 2026 12:00:00 +0100</pubDate>
<description>&lt;p&gt;Der &lt;b&gt;DAX&lt;/b&gt; stieg &amp;amp; fiel.&lt;/p&gt;</description></item>
</channel></rss>""".encode()

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Fed holds rates</title><link href="https://a/1"/><updated>2026-11-03T09:00:00Z</updated>
<summary>Markets calm.</summary></entry></feed>"""


def test_parse_rss_google_style():
    items = news.parse_feed(RSS, "Google News", split_source=True)
    assert items[0].headline == "SAP hebt Prognose an" and items[0].source == "Handelsblatt"
    assert items[0].via == "Google News" and items[0].summary == ""
    assert items[0].published == "2026-11-03T10:00:00+00:00"
    assert items[1].published == "2026-11-03T11:00:00+00:00"


def test_parse_rss_plain_and_atom():
    items = news.parse_feed(RSS, "tagesschau")
    assert items[1].summary == "Der DAX stieg & fiel." and items[1].source == "tagesschau"
    a = news.parse_feed(ATOM, "Atom")
    assert a[0].url == "https://a/1" and a[0].summary == "Markets calm." and a[0].published.startswith("2026-11-03T09")


def test_parse_rejects_entities_and_garbage():
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title></item></channel></rss>'
    assert news.parse_feed(bomb) == []
    assert news.parse_feed(b"<html>kein xml") == []


def test_merge_dedupes_sorts_and_filters_old():
    now = datetime.now(timezone.utc)
    mk = lambda h, d, s="": news.NewsItem(h, s, "x", "u", (now - timedelta(days=d)).isoformat(), 0.0)  # noqa: E731
    out = news.merge([[mk("Apple steigt", 1)], [mk("Apple steigt!", 1, "mit Text"), mk("Neu", 0), mk("Alt", 10)]], 3)
    assert [i.headline for i in out] == ["Neu", "Apple steigt!"]
    assert out[1].summary == "mit Text"


def test_search_name_and_feed_list():
    assert news.search_name("SAP SE") == "SAP"
    assert news.search_name("Apple Inc.") == "Apple"
    assert news.search_name("iShares Core MSCI World UCITS ETF USD (Acc)") == "iShares Core MSCI World"
    assert news.search_name(None, "DE0007164600.GTX") == ""
    assert news.search_name(None, "BTC-EUR") == "BTC EUR"
    assert news.parse_feed_list("A | https://a/rss\n# aus\nhttps://www.b.de/x\nquatsch") == [
        ("A", "https://a/rss"), ("b.de", "https://www.b.de/x")]


def test_collect_uses_enabled_sources(monkeypatch):
    calls = []

    def fake(url, via="", split_source=False):
        calls.append(via)
        return [news.NewsItem(f"SAP {via}", "", "q", url, datetime.now(timezone.utc).isoformat(), 0.0, via)]

    monkeypatch.setattr(news, "fetch_feed", fake)
    s = Settings()
    s.finnhub_api_key = ""
    out = news.collect("DE0007164600.GTX", s, "SAP SE")
    assert sorted(calls) == ["Google News", "Google News"]  # gettex: kein Yahoo
    assert len(out) == 1  # beide Google-Abfragen liefern dieselbe Schlagzeile
    calls.clear()
    news.collect("SAP.DE", s, "SAP SE")
    assert sorted(calls) == ["Google News", "Google News", "Yahoo Finance"]
    calls.clear()
    s.news_google = s.news_yahoo = False
    assert news.collect("SAP.DE", s, "SAP SE") == [] and calls == []


def test_feeds_setting_validation():
    from app import settings_store
    assert settings_store.coerce("news_feeds", " A | https://a/x \n\nhttps://b/y") == "A | https://a/x\nhttps://b/y"
    assert settings_store.coerce("news_feeds", "# B | https://b/y") == "# B | https://b/y"
    try:
        settings_store.coerce("news_feeds", "A | ftp://x")
    except settings_store.SettingError:
        pass
    else:
        raise AssertionError("ungültige Adresse akzeptiert")
