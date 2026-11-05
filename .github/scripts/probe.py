import json, subprocess, sys, time
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests", "yfinance"], check=False)
import requests
B = "https://api.onvista.de/api/v1"
H1 = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
H2 = {**H1, "Referer": "https://www.onvista.de/", "Origin": "https://www.onvista.de"}

def show(label, url, params=None, h=H1):
    try:
        r = requests.get(url, params=params, headers=h, timeout=20)
        body = r.text[:500].replace("\n", " ")
        print(f"## {label} {r.status_code} len={len(r.text)} :: {body}")
        return r
    except Exception as e:
        print(f"## {label} EXC {e}")

for isin, kind in [("DE0007164600", "stocks"), ("IE00B4L5Y983", "funds")]:
    s = requests.get(f"{B}/{kind}/ISIN:{isin}/snapshot", headers=H1, timeout=20).json()
    inst = s["instrument"]; et, ev = inst["entityType"], inst["entityValue"]
    q = [x for x in s["quoteList"]["list"] if x["market"]["codeMarket"] == "_TRO"][0]
    idn = q["market"]["idNotation"]
    print("====", isin, et, ev, idn, q.get("datetimeLast"), q.get("last"), q.get("codeQualityPrice"))
    base = f"{B}/instruments/{et}/{ev}"
    for h, hn in [(H1, "plain"), (H2, "ref")]:
        show(f"chart D1 1m {hn}", f"{base}/chart_history", {"idNotation": idn, "range": "D1", "resolution": "1m"}, h)
        show(f"chart D1 {hn}", f"{base}/chart_history", {"idNotation": idn, "range": "D1"}, h)
        show(f"chart W1 {hn}", f"{base}/chart_history", {"idNotation": idn, "range": "W1"}, h)
        show(f"tas {hn}", f"{base}/times_and_sales", {"idNotation": idn, "limit": 50}, h)
        show(f"intraday {hn}", f"{base}/intraday_history", {"idNotation": idn}, h)
        show(f"eod D1 {hn}", f"{base}/eod_history", {"idNotation": idn, "range": "D1"}, h)
        show(f"notation tas {hn}", f"{B}/notations/{idn}/times_and_sales", {"limit": 50}, h)
        show(f"notation chart {hn}", f"{B}/notations/{idn}/chart_history", {"range": "D1"}, h)

import yfinance as yf
for sym in ["SAP.DE", "SAP.MU", "SAP.F", "EUNL.DE", "IWDA.AS"]:
    try:
        df = yf.Ticker(sym).history(period="1d", interval="1m")
        print("YF", sym, len(df), df.index[-1] if len(df) else None, df["Close"].iloc[-1] if len(df) else None)
        df5 = yf.Ticker(sym).history(period="5d", interval="5m")
        print("YF5", sym, len(df5))
    except Exception as e:
        print("YF", sym, "EXC", e)
try:
    print("YFSEARCH", [ (x.get("symbol"), x.get("exchange")) for x in yf.Search("DE0007164600", max_results=10).quotes])
    print("YFSEARCH", [ (x.get("symbol"), x.get("exchange")) for x in yf.Search("IE00B4L5Y983", max_results=10).quotes])
except Exception as e:
    print("YFSEARCH EXC", e)
print("now", time.strftime("%H:%M:%S", time.gmtime()))
