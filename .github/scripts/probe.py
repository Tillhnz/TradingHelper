import time
import requests
B = "https://api.onvista.de/api/v1"
H = {"User-Agent": "Mozilla/5.0 (TradeHelper)", "Accept": "application/json"}
isins = ["DE0007164600", "DE0005200000", "DE0005936124", "DE0006070006", "DE000A1K0235", "DE000BAY0017", "NL0000235190", "US0378331005"]
t0 = time.time()
codes = []
for i in range(80):
    isin = isins[i % len(isins)]
    r = requests.get(f"{B}/instruments/STOCK/ISIN:{isin}/snapshot", headers=H, timeout=20)
    codes.append(r.status_code)
    if r.status_code == 429 and codes.count(429) == 1:
        print(f"first 429 after {i} requests, {time.time()-t0:.1f}s", dict(r.headers))
    time.sleep(0.3)
print("codes", "".join("." if c == 200 else "X" if c == 429 else "?" for c in codes))
for wait in [15, 30, 60, 120]:
    time.sleep(wait)
    r = requests.get(f"{B}/instruments/STOCK/ISIN:DE0007164600/snapshot", headers=H, timeout=20)
    print(f"after +{wait}s:", r.status_code)
# leichtere Endpunkte?
for path in ["/instruments/STOCK/82849/quote", "/instruments/STOCK/82849/quotes", "/instruments/query?searchValue=DE0007164600&limit=1"]:
    r = requests.get(B + path, headers=H, timeout=20)
    print("light", path, r.status_code, r.text[:600].replace("\n", " "))
