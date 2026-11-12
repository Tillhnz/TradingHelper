import json, time
import requests
B = "https://api.onvista.de/api/v1"
H = {"User-Agent": "Mozilla/5.0 (TradeHelper)", "Accept": "application/json"}
def get(path, **kw):
    r = requests.get(B + path, headers=H, timeout=20, **kw)
    return r.status_code, r
for i in range(3):
    c, r = get("/stocks/ISIN:DE0007164600/snapshot")
    print("stock snap try", i, c, r.headers.get("retry-after"), {k: v for k, v in r.headers.items() if "limit" in k.lower() or "retry" in k.lower()})
    time.sleep(5)
for isin in ["DE0005200000", "NL0000235190", "US0079031078"]:
    print(isin, get(f"/stocks/ISIN:{isin}/snapshot")[0])
c, r = get("/instruments/query", params={"searchValue": "DE0007164600", "limit": 3})
hit = r.json()["list"][0]
print("query keys", list(hit), json.dumps(hit, ensure_ascii=False)[:800])
ev = hit.get("entityValue")
for path in [f"/stocks/{ev}/snapshot", f"/instruments/STOCK/{ev}/snapshot", f"/instruments/STOCK/{ev}", f"/stocks/ISIN:DE0007164600",
             f"/instruments/STOCK/ISIN:DE0007164600/snapshot", f"/instruments/STOCK/{ev}/quote", f"/instruments/STOCK/{ev}/quotes",
             f"/stocks/{ev}/quote_list", f"/instruments/STOCK/{ev}/notations", f"/stocks/ISIN:DE0007164600/quote_list"]:
    c, r = get(path)
    print("ALT", path, c, r.text[:250].replace("\n", " "))
