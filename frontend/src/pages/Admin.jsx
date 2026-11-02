import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { ErrorText, Loading } from "../components/ui.jsx";
import { dateTime } from "../fmt.js";

const JOB_LABEL = { morning_report: "Morgenreport", alert_check: "Alarmprüfung" };

function Status() {
  const [st, setSt] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { api.get("/admin/status").then(setSt).catch((e) => setError(e.message)); }, []);
  return (
    <section className="panel">
      <h2>Zustand</h2>
      <ErrorText error={error} />
      {!st && !error && <Loading text="Prüfe …" />}
      {st && (
        <>
          <ul className="checks">
            {st.checks.map((c) => (
              <li key={c.label}>
                <span className={`check-dot ${c.ok ? "ok" : "bad"}`} aria-hidden="true" />
                <strong>{c.label}</strong> <span className="muted">{c.text}</span>
              </li>
            ))}
          </ul>
          <p className="muted small">
            {st.counts.watchlist} Werte in der Watchlist · {st.counts.alerts} aktive Alarme
            {Object.entries(st.next_runs).map(([k, v]) => ` · ${JOB_LABEL[k] || k}: ${dateTime(v)}`)}
          </p>
        </>
      )}
    </section>
  );
}

function Updates() {
  const [st, setSt] = useState(null);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);
  const [watching, setWatching] = useState(false);

  const load = useCallback(async (check = false) => {
    try {
      const r = await api.get(`/admin/update${check ? "?check=true" : ""}`);
      setSt(r);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(true); }, [load]);

  // Während des Updates regelmäßig nachfragen. Das Backend startet dabei kurz neu, Fehler sind dann normal.
  useEffect(() => {
    if (!watching) return undefined;
    const id = setInterval(async () => {
      try {
        const r = await api.get("/admin/update");
        setSt(r);
        setError("");
        if (r.job.state === "done") { setWatching(false); setTimeout(() => window.location.reload(), 1500); }
        if (r.job.state === "failed") setWatching(false);
      } catch {
        setError("");
      }
    }, 3000);
    return () => clearInterval(id);
  }, [watching]);

  async function check() {
    setChecking(true);
    await load(true);
    setChecking(false);
  }

  async function start() {
    if (!window.confirm("TradeHelper jetzt aktualisieren? Die Seite ist ein bis zwei Minuten nicht erreichbar, deine Daten bleiben erhalten.")) return;
    try {
      await api.post("/admin/update");
      setWatching(true);
      setSt((s) => ({ ...s, job: { ...(s?.job || {}), state: "running", log: "", error: null } }));
    } catch (e) {
      setError(e.message);
    }
  }

  const v = st?.version;
  const job = st?.job;
  const busy = watching || job?.state === "running" || job?.state === "restarting";
  return (
    <section className="panel">
      <h2>Updates</h2>
      {v && <p>Installierte Version: <strong>{v.commit}</strong> <span className="muted small">vom {v.date}, {v.subject}</span></p>}
      {st?.dirty && <p className="error">Im Projektordner gibt es lokale Änderungen. Das Update bricht dann ab.</p>}
      {st?.check_error && <p className="error" role="alert">{st.check_error}</p>}
      {st?.behind === 0 && <p className="ok">TradeHelper ist auf dem neuesten Stand.</p>}
      {st?.behind > 0 && (
        <>
          <p><strong>{st.behind} {st.behind === 1 ? "neue Änderung" : "neue Änderungen"}</strong> verfügbar:</p>
          <ul className="log-list">{st.changes.map((c) => <li key={c}>{c}</li>)}</ul>
        </>
      )}
      {busy && <p role="status" className="note">{job?.state === "restarting" ? "Starte neu … die Seite lädt gleich von selbst." : "Update läuft … das dauert einige Minuten."}</p>}
      {job?.state === "failed" && <p className="error" role="alert">{job.error}</p>}
      {job?.state === "failed" && job.log && <details><summary className="small">Protokoll</summary><pre className="logbox">{job.log}</pre></details>}
      <ErrorText error={error} />
      <div className="actions">
        <button className="btn" onClick={check} disabled={busy || checking}>{checking ? "Prüfe …" : "Nach Updates suchen"}</button>
        <button className="btn primary" onClick={start} disabled={busy || !st || st.behind === 0}>Jetzt aktualisieren</button>
      </div>
      <p className="muted small">
        Das Update sichert zuerst die Datenbank, holt die neue Version von GitHub und baut sie neu. Springt die neue Version
        nicht an, geht TradeHelper automatisch zur vorherigen zurück.
      </p>
    </section>
  );
}

function Backups() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.get("/admin/backups").then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  async function create() {
    setBusy(true);
    setError("");
    try {
      await api.post("/admin/backups");
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <h2>Sicherungen</h2>
      <ErrorText error={error} />
      {data && (data.items.length ? (
        <ul className="log-list">
          {data.items.map((b) => <li key={b.name}><code>{b.name}</code> <span className="muted small">{(b.bytes / 1024).toFixed(0)} KB · {dateTime(b.at)}</span></li>)}
        </ul>
      ) : <p className="muted">Noch keine Sicherung.</p>)}
      <div className="actions">
        <button className="btn" onClick={create} disabled={busy || data?.busy}>{busy ? "Sichere …" : "Jetzt sichern"}</button>
      </div>
      <p className="muted small">
        Liegen im Ordner <code>backups</code> der Installation. Vor jedem Update entsteht automatisch eine, die letzten 14 bleiben.
        Zurückspielen im Container: <code>./install.sh restore DATEI</code>
      </p>
    </section>
  );
}

export default function Admin() {
  return (
    <>
      <div className="page-head"><h1>Administration</h1></div>
      <Status />
      <Updates />
      <Backups />
    </>
  );
}
