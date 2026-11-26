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
t0 = time.time()
try:
    res = brain.run_training(st, settings, horizons=["medium"])
    print("ERGEBNIS", json.dumps(res, default=str)[:3000])
except Exception:
    traceback.print_exc()
print("STATUS", json.dumps(brain.STATUS, default=str))
_, meta = brain.load("medium")
print("META", json.dumps({k: (meta or {}).get(k) for k in ("version", "rows", "symbols", "skill", "summary", "config")}, default=str))
import resource  # noqa: E402

print(f"Dauer {time.time() - t0:.0f} s, Arbeitsspeicher max. {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MB")
sys.exit(0 if meta else 1)
