import json
import requests
H = {"User-Agent": "Mozilla/5.0 (TradeHelper probe)", "Accept": "application/json"}
B = "https://api.onvista.de/api/v1"
snap = requests.get(f"{B}/stocks/ISIN:DE0007164600/snapshot", headers=H, timeout=20).json()
print("FUND 2025", json.dumps(snap["stocksCnFundamentalList"]["list"][1], ensure_ascii=False))
print("FIN 2025", json.dumps(snap["stocksCnFinancialList"]["list"][3], ensure_ascii=False))
for path in ["/etfs/ISIN:IE00B4L5Y983/snapshot", "/funds/ISIN:IE00B4L5Y983/snapshot"]:
    r = requests.get(B + path, headers=H, timeout=20)
    print("ETF", path, r.status_code)
    if r.ok:
        j = r.json()
        print(" keys", list(j))
        for k in j:
            if k not in ("quoteList", "chart", "cnPerformance", "chartBenchmark", "relatedInstrumentItemList", "quote"):
                print(" ", k, json.dumps(j[k], ensure_ascii=False)[:1500])
