import requests
B = "https://api.onvista.de/api/v1"
for ua in ["Mozilla/5.0 (TradeHelper)", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"]:
    H = {"User-Agent": ua, "Accept": "application/json"}
    for path in ["/stocks/ISIN:DE0007164600/snapshot", "/funds/ISIN:IE00B4L5Y983/snapshot", "/instruments/query?searchValue=SAP&limit=2",
                 "/stocks/ISIN:DE0007164600/eod_history?idNotation=0&range=Y1"]:
        try:
            r = requests.get(B + path, headers=H, timeout=20)
            print(ua[:25], path, r.status_code, r.headers.get("content-type"), r.text[:300].replace("\n", " "))
        except Exception as e:
            print(path, "ERR", e)
r = requests.get("https://www.onvista.de/aktien/SAP-Aktie-DE0007164600", headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
print("web", r.status_code, len(r.text))
import re
print(sorted(set(re.findall(r"https://api\.onvista\.de/api/v\d+/[a-zA-Z_/{}:.-]+", r.text)))[:30])
