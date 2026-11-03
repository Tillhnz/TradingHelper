import { useEffect, useState } from "react";
import { api, setToken } from "../api.js";
import { ErrorText, Loading } from "../components/ui.jsx";
import { dateTime } from "../fmt.js";

const GROUPS = [
  {
    id: "strategy",
    title: "Anlagestrategie",
    intro: "Danach richten sich alle Einschätzungen: welche Signale zählen, wann eine Empfehlung kippt, wo der Stopp liegt.",
    fields: {
      invest_horizon: { label: "Anlagehorizont", type: "select", options: ["short", "medium", "long"], labels: { short: "Kurzfristig – Tage bis Wochen", medium: "Mittelfristig – Wochen bis Monate", long: "Langfristig – Jahre" } },
      risk_profile: { label: "Risikobereitschaft", type: "select", options: ["conservative", "balanced", "aggressive"], labels: { conservative: "Konservativ – Verluste begrenzen", balanced: "Ausgewogen", aggressive: "Offensiv – mehr Schwankung für mehr Chance" } },
      portfolio_size: { label: "Depotgröße", type: "number", hint: "optional, in Anzeigewährung – für Vorschläge zur Positionsgröße; 0 = aus" },
    },
  },
  {
    id: "notify",
    title: "Benachrichtigungen",
    intro: "Push-Nachrichten kommen über ntfy. App installieren (Android/iOS), Topic abonnieren, hier denselben Namen eintragen. Bei ntfy.sh ist jedes Topic öffentlich lesbar: wähle einen langen, zufälligen Namen.",
    fields: {
      ntfy_url: { label: "ntfy-Server", hint: "https://ntfy.sh oder dein eigener" },
      ntfy_topic: { label: "Topic", hint: "z. B. tradehelper-x7k2p9" },
      ntfy_token: { label: "Zugangs-Token", hint: "nur bei geschützten Topics" },
    },
  },
  {
    id: "news",
    title: "Nachrichten",
    intro: "Für die News-Stimmung im Report. Kostenlosen Schlüssel auf finnhub.io anlegen (Register → Dashboard → API Key).",
    fields: {
      finnhub_api_key: { label: "Finnhub-Schlüssel" },
      news_lookback_days: { label: "Nachrichten der letzten … Tage", type: "number" },
    },
  },
  {
    id: "schedule",
    title: "Zeitplan",
    intro: "Wann der Morgenreport kommt und wann Alarme geprüft werden.",
    fields: {
      report_enabled: { label: "Morgenreport senden", type: "bool" },
      report_time: { label: "Uhrzeit des Reports", type: "time" },
      report_weekends: { label: "Auch am Wochenende", type: "bool" },
      alerts_enabled: { label: "Alarme automatisch prüfen", type: "bool" },
      alert_interval_minutes: { label: "Prüfen alle … Minuten", type: "select", options: [1, 2, 5, 10, 15, 30, 60] },
      alert_start_hour: { label: "Von (Uhr)", type: "hour" },
      alert_end_hour: { label: "Bis (Uhr)", type: "hour", hint: "kleiner als „Von“ = über Mitternacht" },
      alert_weekends: { label: "Auch am Wochenende (Krypto)", type: "bool" },
      alert_cooldown_minutes: { label: "Pause nach Auslösung (Minuten)", type: "number", hint: "derselbe Alarm meldet sich frühestens danach wieder" },
    },
  },
  {
    id: "general",
    title: "Allgemein",
    intro: "Anzeigewährung: Kurse von Werten in anderer Währung (z. B. Apple an der Nasdaq in USD) werden mit dem Tageskurs umgerechnet. Charts, Indikatoren und Report rechnen dann komplett in dieser Währung. „Handelswährung“ zeigt jeden Wert in der Währung seines Börsenplatzes.",
    fields: {
      display_currency: { label: "Anzeigewährung", type: "select", options: ["EUR", "USD", "CHF", "GBP", "native"], labels: { native: "Handelswährung des Börsenplatzes", EUR: "Euro (€)", USD: "US-Dollar ($)", CHF: "Schweizer Franken", GBP: "Britisches Pfund" } },
      timezone: { label: "Zeitzone", hint: "z. B. Europe/Berlin" },
    },
  },
];

const HORIZON_INFO = {
  short: "Zählt vor allem Momentum: RSI, MACD, Stochastik, Bollinger, EMA 9/21 und Volumen. News fließen zu 40 % ein. Stopp 1,5 × ATR unter Kurs, Ziel am nächsten Widerstand.",
  medium: "Ausgewogene Mischung aus Trend und Momentum. News zu 30 %. Stopp 2,5 × ATR, Ziel am nächsten Widerstand.",
  long: "Zählt vor allem den Trend (200-Tage-Linie, Golden/Death Cross) und das 6-/12-Monats-Momentum; Rücksetzer im Aufwärtstrend gelten als Nachkaufchance. Kurzfristige Oszillatoren spielen kaum eine Rolle, News nur zu 15 %. Weiter Stopp (3,5 × ATR), kein festes Kursziel.",
};
const RISK_INFO = {
  conservative: "Kaufen erst ab Score +0,45, Reduzieren schon ab −0,25. Nie kaufen unter der 200-Tage-Linie. Chance/Risiko mindestens 2. Abschlag bei Schwankung über 4 % pro Tag. Positionen: 0,5 % Depotrisiko, höchstens 5 % des Depots.",
  balanced: "Kaufen ab +0,35, Reduzieren ab −0,35. Unter der 200-Tage-Linie nur mit klarer Bestätigung. Chance/Risiko mindestens 1,5. Positionen: 1 % Depotrisiko, höchstens 10 % des Depots.",
  aggressive: "Kaufen schon ab +0,25, Reduzieren erst ab −0,45. Auch Käufe gegen den Trend (überverkaufte Rebounds). Chance/Risiko ab 1. Positionen: 2 % Depotrisiko, höchstens 20 % des Depots.",
};

const JOB_LABEL = { morning_report: "Nächster Morgenreport", alert_check: "Nächste Alarmprüfung" };

function Field({ name, spec, entry, value, onChange, onClear }) {
  const id = `f-${name}`;
  if (spec.type === "bool") {
    return (
      <label className="check span-all" htmlFor={id}>
        <input id={id} type="checkbox" checked={!!value} onChange={(e) => onChange(e.target.checked)} />
        {spec.label}
      </label>
    );
  }
  let input;
  if (entry.secret) {
    input = (
      <input id={id} type="password" autoComplete="off" value={value ?? ""} onChange={(e) => onChange(e.target.value)}
        placeholder={entry.set ? "gespeichert – leer lassen zum Behalten" : "nicht gesetzt"} />
    );
  } else if (spec.type === "select") {
    input = (
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {spec.options.map((o) => <option key={o} value={o}>{spec.labels?.[o] ?? o}</option>)}
      </select>
    );
  } else if (spec.type === "hour") {
    input = (
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {Array.from({ length: 24 }, (_, h) => <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>)}
      </select>
    );
  } else {
    input = <input id={id} type={spec.type || "text"} value={value ?? ""} onChange={(e) => onChange(e.target.value)} />;
  }
  return (
    <label htmlFor={id}>
      <span>{spec.label} {spec.hint && <span className="hint">{spec.hint}</span>}</span>
      {input}
      {entry.secret && entry.set && <button type="button" className="link danger small left" onClick={onClear}>Gespeicherten Wert entfernen</button>}
    </label>
  );
}

function Password() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setMsg("");
    setError("");
    try {
      const r = await api.post("/auth/password", { current, new: next });
      setToken(r.token);
      setCurrent("");
      setNext("");
      setMsg("Passwort geändert. Andere Geräte müssen sich neu anmelden.");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="panel" onSubmit={submit}>
      <h2>Konto</h2>
      <div className="form-grid">
        <label>Aktuelles Passwort<input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required /></label>
        <label>Neues Passwort <span className="hint">mindestens 8 Zeichen</span><input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={8} required /></label>
      </div>
      <div className="actions"><button className="btn">Passwort ändern</button></div>
      {msg && <p className="ok">{msg}</p>}
      <ErrorText error={error} />
    </form>
  );
}

export default function Settings() {
  const [fields, setFields] = useState(null);
  const [values, setValues] = useState({});
  const [dirty, setDirty] = useState({});
  const [nextRuns, setNextRuns] = useState({});
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  function adopt(r) {
    setFields(r.fields);
    setNextRuns(r.next_runs || {});
    setValues(Object.fromEntries(Object.entries(r.fields).map(([k, f]) => [k, f.secret ? "" : f.value])));
    setDirty({});
  }

  useEffect(() => {
    api.get("/settings").then(adopt).catch((e) => setError(e.message));
  }, []);

  function change(key, value) {
    setValues((v) => ({ ...v, [key]: value }));
    setDirty((d) => ({ ...d, [key]: true }));
  }

  async function save(e) {
    e?.preventDefault();
    setSaving(true);
    setError("");
    setMsg("");
    const payload = {};
    for (const key of Object.keys(dirty)) {
      const f = fields[key];
      if (f.secret && values[key] === "" && values[key] !== null) continue; // leer = behalten
      payload[key] = values[key] === null ? "" : values[key];
    }
    try {
      adopt(await api.put("/settings", payload));
      setMsg("Gespeichert.");
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function clearSecret(key) {
    setValues((v) => ({ ...v, [key]: null }));
    setDirty((d) => ({ ...d, [key]: true }));
  }

  async function testNotify() {
    setTesting(true);
    setError("");
    setMsg("");
    try {
      if (Object.keys(dirty).length && !(await save())) return;
      await api.post("/settings/test-notify");
      setMsg("Testnachricht gesendet. Kommt sie nicht an, Topic in der ntfy-App prüfen.");
    } catch (err) {
      setError(err.message);
    } finally {
      setTesting(false);
    }
  }

  if (!fields) return error ? <ErrorText error={error} /> : <Loading />;
  const hasChanges = Object.keys(dirty).length > 0;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Einstellungen</h1>
          <p className="muted">Alles wird sofort übernommen, ein Neustart ist nicht nötig.</p>
        </div>
      </div>

      {Object.keys(nextRuns).length > 0 && (
        <p className="note">
          {Object.entries(nextRuns).map(([k, v]) => <span key={k} className="next-run">{JOB_LABEL[k] || k}: <strong>{dateTime(v)}</strong></span>)}
        </p>
      )}

      <form onSubmit={save}>
        {GROUPS.map((g) => (
          <section key={g.id} className="panel">
            <h2>{g.title}</h2>
            {g.intro && <p className="muted small">{g.intro}</p>}
            <div className="form-grid">
              {Object.entries(g.fields).map(([key, spec]) => fields[key] && (
                <Field key={key} name={key} spec={spec} entry={fields[key]} value={values[key]}
                  onChange={(v) => change(key, v)} onClear={() => clearSecret(key)} />
              ))}
            </div>
            {g.id === "strategy" && (
              <div className="strategy-info">
                <p><strong>{values.invest_horizon === "short" ? "Kurzfristig" : values.invest_horizon === "long" ? "Langfristig" : "Mittelfristig"}:</strong> {HORIZON_INFO[values.invest_horizon]}</p>
                <p><strong>{values.risk_profile === "conservative" ? "Konservativ" : values.risk_profile === "aggressive" ? "Offensiv" : "Ausgewogen"}:</strong> {RISK_INFO[values.risk_profile]}</p>
              </div>
            )}
            {g.id === "notify" && (
              <div className="actions">
                <button type="button" className="btn" onClick={testNotify} disabled={testing}>{testing ? "Sende …" : "Testnachricht senden"}</button>
              </div>
            )}
          </section>
        ))}
        <div className={`save-bar ${hasChanges ? "show" : ""}`}>
          <span>{hasChanges ? "Ungespeicherte Änderungen" : ""}</span>
          <button className="btn primary" disabled={saving || !hasChanges}>{saving ? "Speichere …" : "Speichern"}</button>
        </div>
      </form>
      {msg && <p className="ok" role="status">{msg}</p>}
      <ErrorText error={error} />

      <Password />
    </>
  );
}
