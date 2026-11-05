import json, requests
B = "https://api.onvista.de/api/v1"
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
for isin, kind in [("DE0007164600", "stocks"), ("IE00B4L5Y983", "funds")]:
    s = requests.get(f"{B}/{kind}/ISIN:{isin}/snapshot", headers=H, timeout=20).json()
    inst = s["instrument"]; et, ev = inst["entityType"], inst["entityValue"]
    q = [x for x in s["quoteList"]["list"] if x["market"]["codeMarket"] == "_TRO"][0]
    idn = q["market"]["idNotation"]
    base = f"{B}/instruments/{et}/{ev}/times_and_sales"
    for params in [{"idNotation": idn}, {"idNotation": idn, "limit": 5000}, {"idNotation": idn, "limit": 100000},
                   {"idNotation": idn, "limit": 1000, "order": "ASC"}, {"idNotation": idn, "startDate": "2026-11-04"},
                   {"idNotation": idn, "page": 2, "limit": 50}]:
        r = requests.get(base, params=params, headers=H, timeout=20)
        if not r.ok:
            print(params, r.status_code, r.text[:200]); continue
        d = r.json()
        info = {k: (len(v) if isinstance(v, list) else v) for k, v in d.items()}
        print(params, json.dumps(info)[:900])
        for k in d:
            if isinstance(d[k], list) and d[k]:
                print("   ", k, d[k][:3], "...", d[k][-2:])
