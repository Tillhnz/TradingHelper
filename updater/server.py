"""Update-Dienst für TradeHelper.

Läuft als eigener Container ohne veröffentlichten Port. Nur das Backend erreicht ihn im internen Netz, und nur mit
dem gemeinsamen Token. Er holt per git die neue Version und baut Backend und Frontend neu. Vorher sichert er die
SQLite-Datenbank. An den Daten und an der .env ändert er nichts.
"""
import gzip
import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PROJECT = "/project"
DB_FILE = os.path.join(PROJECT, "data", "tradehelper.db")
BACKUPS = os.path.join(PROJECT, "backups")
BACKUP_RE = r"tradehelper-\d{8}-\d{6}\.db\.gz"
KEEP_BACKUPS = 14
TOKEN = hashlib.sha256(("updater:" + os.environ.get("SECRET_KEY", "")).encode()).hexdigest()
HEALTH_URL = "http://backend:8000/api/health"
SERVICES = ["backend", "frontend"]  # der Update-Dienst baut sich nicht selbst neu, das macht ./install.sh update

lock = threading.Lock()
job = {"state": "idle", "log": "", "started": None, "error": None, "before": None}


_host_dir = None


def host_dir():
    """Pfad des Projektordners auf dem Server (Quelle des Mounts /project). Docker Compose braucht ihn, damit
    Ordner wie ./data beim Neuanlegen der Container auf den echten Ordner zeigen und nicht auf /project/data."""
    global _host_dir
    if _host_dir is None:
        p = subprocess.run(
            ["docker", "inspect", "-f", '{{range .Mounts}}{{if eq .Destination "/project"}}{{.Source}}{{end}}{{end}}',
             os.environ.get("HOSTNAME", "")], capture_output=True, text=True, timeout=20)
        _host_dir = p.stdout.strip() or os.environ.get("PROJECT_DIR", "")
    return _host_dir


def run(cmd, timeout=1800, log=False):
    env = dict(os.environ)
    if cmd[:1] == ["docker"] and host_dir():
        env["PROJECT_DIR"] = host_dir()
    p = subprocess.run(cmd, cwd=PROJECT, capture_output=True, text=True, timeout=timeout, env=env)
    out = (p.stdout or "") + (p.stderr or "")
    if log:
        job["log"] = (job["log"] + f"$ {' '.join(cmd)}\n{out}\n")[-20000:]
    return p.returncode, out.strip()


def project_name():
    code, out = run(["docker", "inspect", "-f", '{{ index .Config.Labels "com.docker.compose.project" }}',
                     os.environ.get("HOSTNAME", "")], 20)
    return out if code == 0 and out else None


def compose_base():
    name = project_name()
    if not name:
        raise RuntimeError("Der Projektname von Docker Compose wurde nicht gefunden.")
    return ["docker", "compose", "-p", name, "--project-directory", PROJECT]


def make_backup():
    """Konsistente Kopie der SQLite-Datenbank (Online-Backup-API), gzip-komprimiert, alte werden aufgeräumt."""
    if not os.path.exists(DB_FILE):
        raise RuntimeError("Es gibt noch keine Datenbank zum Sichern.")
    os.makedirs(BACKUPS, exist_ok=True)
    name = datetime.now().strftime("tradehelper-%Y%m%d-%H%M%S.db.gz")
    path = os.path.join(BACKUPS, name)
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        src = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
        dst = sqlite3.connect(tmp)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        with open(tmp, "rb") as f_in, gzip.open(path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        os.chmod(path, 0o600)
    except Exception:
        if os.path.exists(path):
            os.remove(path)
        raise
    finally:
        os.remove(tmp)
    for old in sorted(f for f in os.listdir(BACKUPS) if re.fullmatch(BACKUP_RE, f))[:-KEEP_BACKUPS]:
        os.remove(os.path.join(BACKUPS, old))
    return name


def list_backups():
    if not os.path.isdir(BACKUPS):
        return []
    out = []
    for f in sorted((f for f in os.listdir(BACKUPS) if re.fullmatch(BACKUP_RE, f)), reverse=True):
        st = os.stat(os.path.join(BACKUPS, f))
        out.append({"name": f, "bytes": st.st_size, "at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    return out


def wait_healthy(seconds=150):
    end = time.time() + seconds
    while time.time() < end:
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False


def version():
    code, out = run(["git", "log", "-1", "--format=%h%x09%cs%x09%s"], 20)
    if code != 0:
        return None
    h, d, s = (out.split("\t") + ["", ""])[:3]
    return {"commit": h, "date": d, "subject": s}


def status(check):
    res = {"version": version(), "job": dict(job), "behind": None, "changes": [], "check_error": None, "dirty": False}
    _, out = run(["git", "status", "--porcelain", "--untracked-files=no"], 20)
    res["dirty"] = bool(out)
    if check and job["state"] != "running":
        code, out = run(["git", "fetch", "--quiet"], 60)
        if code != 0:
            res["check_error"] = "Die neue Version konnte nicht abgefragt werden: " + out[-300:]
            return res
        code, out = run(["git", "rev-list", "--count", "HEAD..@{u}"], 20)
        if code != 0:
            res["check_error"] = "Der Ordner folgt keinem Zweig auf GitHub."
            return res
        res["behind"] = int(out or 0)
        if res["behind"]:
            _, log = run(["git", "log", "HEAD..@{u}", "--format=%cs  %s", "-n", "15"], 20)
            res["changes"] = log.splitlines()
    return res


def do_update():
    try:
        if not host_dir():
            raise RuntimeError("Der Projektordner auf dem Server wurde nicht gefunden. Bitte einmal im Terminal: ./install.sh update")
        base = compose_base()
        _, before = run(["git", "rev-parse", "HEAD"], 20)
        job["before"] = before
        if os.path.exists(DB_FILE):
            job["log"] += f"Sicherung: {make_backup()}\n"
        code, _ = run(["git", "pull", "--ff-only"], 300, log=True)
        if code != 0:
            raise RuntimeError("git pull ist fehlgeschlagen. Lokale Änderungen im Projektordner oder GitHub nicht erreichbar.")
        code, _ = run(base + ["build", "--pull", *SERVICES], 3000, log=True)
        if code != 0:
            run(["git", "reset", "--keep", before], 60, log=True)
            raise RuntimeError("Der Bau der neuen Version ist fehlgeschlagen. Die laufende Version bleibt unverändert.")
        job["state"] = "restarting"
        code, _ = run(base + ["up", "-d", *SERVICES], 600, log=True)
        if code != 0 or not wait_healthy():
            job["log"] += "Die neue Version startet nicht. Gehe zur vorherigen Version zurück …\n"
            run(["git", "reset", "--keep", before], 60, log=True)
            run(base + ["build", "--pull", *SERVICES], 3000, log=True)
            run(base + ["up", "-d", *SERVICES], 600, log=True)
            raise RuntimeError("Die neue Version ist nicht angesprungen. TradeHelper läuft wieder mit der vorherigen Version.")
        job["state"] = "done"
    except Exception as e:
        job["state"], job["error"] = "failed", str(e)
    finally:
        lock.release()


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _auth(self):
        if hmac.compare_digest(self.headers.get("X-Updater-Token", ""), TOKEN):
            return True
        self._send(401, {"error": "unauthorized"})
        return False

    def do_GET(self):
        if not self._auth():
            return
        if self.path.startswith("/status"):
            self._send(200, status("check=1" in self.path))
        elif self.path == "/backups":
            self._send(200, {"items": list_backups(), "busy": job["state"] in ("running", "restarting")})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._auth():
            return
        if self.path == "/backups":
            if not lock.acquire(blocking=False):
                return self._send(409, {"error": "Es läuft gerade ein Update."})
            try:
                return self._send(201, {"name": make_backup()})
            except Exception as e:
                return self._send(502, {"error": str(e)})
            finally:
                lock.release()
        if self.path != "/update":
            return self._send(404, {"error": "not found"})
        if not lock.acquire(blocking=False):
            return self._send(409, {"error": "Es läuft bereits ein Update."})
        job.update(state="running", log="", error=None, started=datetime.now().isoformat(timespec="seconds"))
        threading.Thread(target=do_update, daemon=True).start()
        self._send(202, {"ok": True})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
