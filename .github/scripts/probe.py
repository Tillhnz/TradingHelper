import urllib.request, urllib.parse, xml.etree.ElementTree as ET, json
H = {"User-Agent": "Mozilla/5.0 (TradeHelper)", "Accept": "application/rss+xml, application/xml, text/xml, */*"}
def rss(name, url):
    try:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=20).read()
        root = ET.fromstring(raw)
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
        first = items[0] if items else None
        t = first.findtext("title") if first is not None else None
        d = (first.findtext("pubDate") or first.findtext("{http://www.w3.org/2005/Atom}updated")) if first is not None else None
        src = first.find("source").text if first is not None and first.find("source") is not None else None
        print(f"OK   {name}: {len(items)} items | {d} | {src} | {t[:90] if t else t}")
    except Exception as e:
        print(f"FAIL {name}: {e}")
q = lambda s, hl="de", gl="DE": f"https://news.google.com/rss/search?q={urllib.parse.quote(s)}&hl={hl}&gl={gl}&ceid={gl}:{hl}"
rss("google de SAP", q("SAP Aktie when:7d"))
rss("google en Apple", q("Apple stock when:7d", "en-US", "US"))
rss("google de Beiersdorf", q('"Beiersdorf" Aktie when:7d'))
rss("google de business top", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=de&gl=DE&ceid=DE:de")
rss("yahoo rss AAPL", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL&region=US&lang=en-US")
rss("tagesschau wirtschaft", "https://www.tagesschau.de/wirtschaft/index~rss2.xml")
rss("tagesschau finanzen", "https://www.tagesschau.de/wirtschaft/finanzen/index~rss2.xml")
rss("handelsblatt finanzen", "https://www.handelsblatt.com/contentexport/feed/finanzen")
rss("handelsblatt top", "https://www.handelsblatt.com/contentexport/feed/schlagzeilen")
rss("ntv wirtschaft", "https://www.n-tv.de/wirtschaft/rss")
rss("finanzen.net news", "https://www.finanzen.net/rss/news")
rss("spiegel wirtschaft", "https://www.spiegel.de/wirtschaft/index.rss")
rss("faz finanzen", "https://www.faz.net/rss/aktuell/finanzen/")
rss("marketwatch top", "https://feeds.content.dowjones.io/public/rss/mw_topstories")
rss("marketwatch markets", "https://feeds.content.dowjones.io/public/rss/mw_marketpulse")
rss("cnbc markets", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258")
rss("cnbc top", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114")
rss("boerse.de", "https://www.boerse.de/rss/nachrichten/")
rss("investing de", "https://de.investing.com/rss/news.rss")
try:
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "yfinance"], check=True)
    import yfinance as yf
    n = yf.Ticker("AAPL").news
    print("yfinance AAPL news", len(n), json.dumps(n[0])[:400] if n else None)
    n2 = yf.Ticker("SAP.DE").news
    print("yfinance SAP.DE news", len(n2), json.dumps(n2[0])[:300] if n2 else None)
except Exception as e:
    print("yfinance FAIL", e)
