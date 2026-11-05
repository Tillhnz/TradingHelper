import json, requests, time
B = "https://api.onvista.de/api/v1"
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
for isin, kind in [("DE0007164600", "stocks"), ("IE00B4L5Y983", "funds"), ("NL0000235190", "stocks")]:
    s = requests.get(f"{B}/{kind}/ISIN:{isin}/snapshot", headers=H, timeout=20).json()
    q = [x for x in s["quoteList"]["list"] if x["market"]["codeMarket"] == "_TRO"][0]
    print(isin, json.dumps({k: v for k, v in q.items() if k != "market"})[:1500])
    for key in s:
        if "bid" in key.lower() or "orderbook" in key.lower() or "quote" in key.lower():
            print("  key", key)
    inst = s["instrument"]
    for path in ["bid_ask", "orderbook", "quotes_bid_ask"]:
        r = requests.get(f"{B}/instruments/{inst['entityType']}/{inst['entityValue']}/{path}", params={"idNotation": q["market"]["idNotation"]}, headers=H, timeout=20)
        print("  ", path, r.status_code, r.text[:300])
    print("  now", int(time.time()))
