import json, subprocess, sys
import requests
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
B = "https://api.onvista.de/api/v1"

def keys(d, depth=0, pre=""):
    if depth > 2 or not isinstance(d, dict):
        return
    for k, v in d.items():
        if isinstance(v, dict):
            print(" " * depth * 2 + pre + k + " {")
            keys(v, depth + 1)
        elif isinstance(v, list):
            print(" " * depth * 2 + k, f"[list {len(v)}]", json.dumps(v[:1], ensure_ascii=False)[:400])
        else:
            print(" " * depth * 2 + k, "=", str(v)[:200])

for isin in ["DE0007164600", "US0378331005"]:
    r = requests.get(f"{B}/stocks/ISIN:{isin}/snapshot", headers=H, timeout=20)
    print("=====", isin, r.status_code)
    snap = r.json()
    for k in snap:
        if k in ("quoteList", "instrument"): continue
        print("##", k)
        keys(snap[k])
r = requests.get(f"{B}/funds/ISIN:IE00B4L5YY83/snapshot", headers=H, timeout=20)
print("===== ETF", r.status_code)
for k, v in r.json().items():
    if k in ("quoteList",): continue
    print("##", k); keys(v)

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "yfinance"], check=False)
import yfinance as yf
try:
    info = yf.Ticker("SAP.DE").info
    print("===== yfinance SAP.DE", len(info))
    for k in ["longBusinessSummary", "sector", "industry", "fullTimeEmployees", "marketCap", "trailingPE", "forwardPE",
              "dividendYield", "profitMargins", "revenueGrowth", "beta", "priceToBook", "totalRevenue", "website", "country"]:
        print(k, "=", str(info.get(k))[:200])
except Exception as e:
    print("yf error", e)
