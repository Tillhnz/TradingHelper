import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { ErrorText, Loading } from "../components/ui.jsx";
import { dateTime } from "../fmt.js";

const JOB_LABEL = {
  morning_report: "Morgenbericht", afternoon_report: "Nachmittagsbericht", alert_check: "Alarmprüfung",
  paper_orders: "Schattendepot-Orders", paper_backtest: "Rückblick", update_watch: "Update-Prüfung",
};
const RUN_STATUS = { ok: ["ok", "erledigt"], warn: ["warn", "mit Problem"], error: ["bad", "Fehler"], running: ["warn", "läuft"] };

function JobRuns({ runs }) {
  if (!runs?.length) return <p className="muted small">Noch keine Berichte gelaufen (das Protokoll gibt es ab Version 0.15.1).</p>;
  return (
    <ul className="checks job-runs">
      {runs.slice(0, 15).map((r) => {
        const [cls, label] = RUN_STATUS[r.status] || ["warn", r.status];
        return (
          <li key={r.id}>
            <span className={`check-dot ${cls}`} aria-hidden="true" />
            <strong>{JOB_LABEL[r.job] || r.job}</strong>{" "}
            <span className="muted small">{dateTime(r.started_at)}{r.username ? ` · ${r.username}` : ""} · {label}</span>
            {r.detail && <div className="small muted job-detail">{r.detail}</div>}
          </li>
        );
      })}
    </ul>
  );
}

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
            {st.counts.users} {st.counts.users === 1 ? "Nutzer" : "Nutzer"} · deine Watchlist: {st.counts.watchlist} Werte · {st.counts.alerts} aktive Alarme
          </p>
          <h3 className="sub-head">Zeitplan</h3>
          <ul className="muted small plain-list">
            {Object.entries(st.next_runs).map(([k, v]) => <li key={k}>{JOB_LABEL[k] || k}: nächster Lauf {v ? dateTime(v) : "–"}</li>)}
          </ul>
          <h3 className="sub-head">Letzte Berichte</h3>
          <JobRuns runs={st.job_runs} />
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

function Users() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [link, setLink] = useState(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => api.get("/users").then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  async function invite(e) {
    e.preventDefault();
    setError("");
    setCopied(false);
    try {
      const r = await api.post("/users/invites", { note, days: 7 });
      setLink(`${window.location.origin}${r.path}`);
      setNote("");
      load();
    } catch (err) { setError(err.message); }
  }

  async function copy() {
    try { await navigator.clipboard.writeText(link); setCopied(true); } catch { setCopied(false); }
  }

  async function share() {
    try { await navigator.share({ title: "Einladung zu TradeHelper", text: "Hier kannst du dein TradeHelper-Konto anlegen:", url: link }); } catch { /* abgebrochen */ }
  }

  async function removeUser(u) {
    if (!window.confirm(`${u.username} mit Watchlist, Depot, Alarmen und Schattendepot endgültig löschen?`)) return;
    await api.del(`/users/${u.id}`).catch((e) => setError(e.message));
    load();
  }

  async function removeInvite(i) {
    await api.del(`/users/invites/${i.id}`).catch((e) => setError(e.message));
    load();
  }

  const open = (data?.invites || []).filter((i) => !i.used_at);
  return (
    <section className="panel" id="nutzer">
      <h2>Nutzer</h2>
      <p className="muted small">
        Eingeladene bekommen ein eigenes Konto mit eigener Watchlist, eigenem Depot, eigenen Alarmen, eigenem Schattendepot
        und eigenen Push-Nachrichten. Updates, Sicherungen, Zeitplan und Nachrichtenquellen bleiben bei dir.
      </p>
      <ErrorText error={error} />
      {!data && !error && <Loading />}
      {data && (
        <ul className="user-list">
          {data.users.map((u) => (
            <li key={u.id}>
              <strong>{u.username}</strong>
              <span className="muted small">{u.is_admin ? "Admin" : `seit ${dateTime(u.created_at)}`}</span>
              {!u.is_admin && <button className="link danger small" onClick={() => removeUser(u)}>Löschen</button>}
            </li>
          ))}
        </ul>
      )}
      <form className="invite-form" onSubmit={invite}>
        <label>Für wen? <span className="hint">optional, nur zur Erinnerung</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={80} placeholder="z. B. Anna" />
        </label>
        <button className="btn primary">Einladungslink erstellen</button>
      </form>
      {link && (
        <div className="invite-link">
          <p className="small">Der Link gilt 7 Tage und funktioniert genau einmal. Er wird nur jetzt angezeigt:</p>
          <code>{link}</code>
          <div className="actions">
            <button className="btn small" onClick={copy}>{copied ? "Kopiert ✓" : "Kopieren"}</button>
            {navigator.share && <button className="btn small" onClick={share}>Teilen …</button>}
          </div>
          {link.includes("localhost") && <p className="muted small">Hinweis: Mit „localhost“ funktioniert der Link nur auf diesem Gerät. Öffne TradeHelper über die Adresse im Netzwerk und erstelle den Link dort.</p>}
        </div>
      )}
      {open.length > 0 && (
        <>
          <h3 className="sub-title">Offene Einladungen</h3>
          <ul className="user-list">
            {open.map((i) => (
              <li key={i.id}>
                <span>{i.note || "ohne Notiz"}</span>
                <span className="muted small">gültig bis {dateTime(i.expires_at)}</span>
                <button className="link danger small" onClick={() => removeInvite(i)}>Zurückziehen</button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

export default function Admin() {
  return (
    <>
      <div className="page-head"><h1>Administration</h1></div>
      <Users />
      <Status />
      <Updates />
      <Backups />
    </>
  );
}
