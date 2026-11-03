import json, urllib.request
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
snap = json.loads(urllib.request.urlopen(urllib.request.Request("https://api.onvista.de/api/v1/stocks/ISIN:DE0007164600/snapshot", headers=H), timeout=20).read())
for q in snap["quoteList"]["list"]:
    if q["market"]["codeMarket"] == "_TRO":
        print("GETTEX", json.dumps({k: v for k, v in q.items() if k != "market"}, ensure_ascii=False))
