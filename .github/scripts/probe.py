import json, urllib.request, urllib.parse, datetime
H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"ERROR": str(e)}
def show(title, obj, n=2500):
    print("=====", title); print(json.dumps(obj, ensure_ascii=False)[:n])

B = "https://api.onvista.de/api/v1"
q = get(f"{B}/instruments/query?searchValue=Apple&limit=5")
for x in q.get("list", [])[:5]:
    print("search", x.get("entityType"), x.get("name"), x.get("isin"), x.get("symbol"), x.get("displayType"))
for kind, isin in [("stocks", "DE0007164600"), ("stocks", "US0378331005"), ("funds", "IE00B4L5Y983")]:
    snap = get(f"{B}/{kind}/ISIN:{isin}/snapshot")
    print("===== snapshot keys", isin, list(snap.keys()) if isinstance(snap, dict) else type(snap))
    inst = snap.get("instrument", {})
    print("instrument", {k: inst.get(k) for k in ("entityType", "entityValue", "name", "isin", "symbol")})
    for key in ("quoteList", "quote"):
        v = snap.get(key)
        print("---", key, json.dumps(v, ensure_ascii=False)[:600])
    ql = (snap.get("quoteList") or {}).get("list", [])
    for x in ql:
        m = x.get("market", {})
        print("market", m.get("name"), m.get("codeMarket"), "idNotation", x.get("idNotation"), x.get("isoCurrency"), x.get("last"), x.get("datetimeLast"))
    gat = [x for x in ql if x.get("market", {}).get("codeMarket") == "_TRO"]
    print("gettex entry", json.dumps(gat[0] if gat else None, ensure_ascii=False)[:900])
    if gat:
        idn = gat[0]["market"]["idNotation"]; ev = inst.get("entityValue"); et = inst.get("entityType")
        start = (datetime.date.today()-datetime.timedelta(days=365)).isoformat()
        for path in [f"/instruments/{et}/{ev}/eod_history?idNotation={idn}&range=Y1&startDate={start}",
                     f"/instruments/{et}/{ev}/eod_history?idNotation={idn}&range=Y5&startDate=" + (datetime.date.today()-datetime.timedelta(days=1825)).isoformat(),
                     f"/instruments/{et}/{ev}/chart_history?resolution=1D&range=Y1&idNotation={idn}",
                     f"/instruments/{et}/{ev}/chart_history?resolution=1H&range=M1&idNotation={idn}",
                     f"/instruments/{et}/{ev}/chart_history?resolution=15M&range=D5&idNotation={idn}",
                     f"/instruments/{et}/{ev}/times_and_sales?idNotation={idn}&limit=3"]:
            r = get(B + path)
            show(path, {k: (v[:3] if isinstance(v, list) else v) for k, v in r.items()} if isinstance(r, dict) else r, 1200)
            if isinstance(r, dict):
                print("lengths", {k: len(v) for k, v in r.items() if isinstance(v, list)})
