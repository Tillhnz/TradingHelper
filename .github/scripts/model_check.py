"""Echtes Training mit echten Kursen – findet heraus, ob das lernende Modell auf einem frischen Server
tatsächlich ein Modell erzeugt. Läuft in GitHub Actions (mit Internet)."""

import json
import logging
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, "backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from app import brain, marketstore  # noqa: E402
from app.config import settings  # noqa: E402
from app.storage import Storage  # noqa: E402

tmp = Path(tempfile.mkdtemp())
marketstore.open_store(tmp / "market.db")
object.__setattr__(settings, "data_dir", tmp)
st = Storage(tmp / "app.db")

# Wie auf einem echten Server nach ein paar Wochen Betrieb: News-Stimmung gibt es nur für die letzten Tage.
# Genau das brach das Lernen ab („window shape cannot be larger than input array shape“).
import pandas as pd  # noqa: E402

store = marketstore.get_store()
recent = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=25)
for i, sym in enumerate(brain.BASE_UNIVERSE[:40]):
    store.put(f"news_hist:{sym}", {str(d.date()): round(((i + j) % 7 - 3) / 5, 2) for j, d in enumerate(recent)})
t0 = time.time()
try:
    res = brain.run_training(st, settings, horizons=["short", "medium"])
    print("ERGEBNIS", json.dumps(res, default=str)[:3000])
except Exception:
    traceback.print_exc()
print("STATUS", json.dumps(brain.STATUS, default=str))
_, meta = brain.load("medium")
print("META", json.dumps({k: (meta or {}).get(k) for k in ("version", "rows", "symbols", "skill", "summary", "config")}, default=str))
import resource  # noqa: E402

print(f"Dauer {time.time() - t0:.0f} s, Arbeitsspeicher max. {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB")
sys.exit(0 if meta else 1)
