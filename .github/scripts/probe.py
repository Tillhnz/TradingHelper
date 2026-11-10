import json, subprocess, sys
import requests
H = {"User-Agent": "Mozilla/5.0 (TradeHelper probe)", "Accept": "application/json"}
B = "https://api.onvista.de/api/v1"
snap = requests.get(f"{B}/stocks/ISIN:DE0007164600/snapshot", headers=H, timeout=20).json()
print("COMPANY", json.dumps(snap["company"], ensure_ascii=False)[:1500])
print("FIGURE", json.dumps(snap["stocksFigure"], ensure_ascii=False)[:1500])
fl = snap["stocksCnFundamentalList"]["list"]
print("FUND labels", [x["label"] for x in fl])
print("FUND last", json.dumps(fl[-1], ensure_ascii=False)[:3000])
fin = snap["stocksCnFinancialList"]["list"]
print("FIN labels", [x["label"] for x in fin])
print("FIN 2025", json.dumps(fin[-3], ensure_ascii=False)[:3000])
bs = snap["stocksBalanceSheetList"]["list"]
print("BS labels", [x["label"] for x in bs])
print("BS last", json.dumps(bs[-1], ensure_ascii=False)[:2500])
print("PROFILE", json.dumps(snap.get("profile"), ensure_ascii=False)[:800])
for path in ["/etfs/ISIN:IE00B4L5YY83/snapshot", "/funds/ISIN:IE00B4L5YY83/snapshot", "/stocks/ISIN:IE00B4L5YY83/snapshot"]:
    r = requests.get(B + path, headers=H, timeout=20)
    print("ETF", path, r.status_code)
    if r.ok:
        j = r.json()
        print(" keys", list(j))
        for k in j:
            if k not in ("quoteList", "chart", "cnPerformance", "chartBenchmark", "relatedInstrumentItemList"):
                print(" ", k, json.dumps(j[k], ensure_ascii=False)[:900])
        break
for q in ["SAP SE", "Apple Inc.", "Allianz SE"]:
    r = requests.get("https://de.wikipedia.org/w/api.php", params={"action": "query", "list": "search", "srsearch": q, "format": "json", "srlimit": 3}, headers=H, timeout=20)
    hits = r.json()["query"]["search"]
    print("WIKI search", q, [h["title"] for h in hits])
    t = hits[0]["title"]
    s = requests.get(f"https://de.wikipedia.org/api/rest_v1/page/summary/{t.replace(' ', '_')}", headers=H, timeout=20).json()
    print("WIKI", t, s.get("description"), "|", s.get("extract", "")[:500])
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", "yfinance"], check=False)
import yfinance as yf
for t in ["SAP.DE", "IWDA.AS"]:
    try:
        info = yf.Ticker(t).info
        print("===== yfinance", t, len(info))
        for k in ["longBusinessSummary", "sector", "industry", "fullTimeEmployees", "marketCap", "trailingPE", "forwardPE",
                  "dividendYield", "profitMargins", "revenueGrowth", "beta", "priceToBook", "totalRevenue", "website", "country",
                  "category", "fundFamily", "totalAssets", "netExpenseRatio", "annualReportExpenseRatio", "fundInceptionDate"]:
            print(" ", k, "=", str(info.get(k))[:300])
    except Exception as e:
        print("yf error", t, e)
