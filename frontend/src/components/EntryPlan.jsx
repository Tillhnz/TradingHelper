import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { money } from "../fmt.js";

const KIND_LABEL = { now: "Sofort", pullback: "Rücksetzer", breakout: "Ausbruch", rebound: "Rebound" };
const PRICE_KINDS = ["price_above", "price_below", "cross_up", "cross_down"];

/** Einstiegsplan: Kursmarken mit Zone, Stopp, Ziel und Warte-Signale, jeweils mit Alarm per Klick. */
export default function EntryPlan({ symbol, plan, currency, nativeCurrency, held = false }) {
  const [done, setDone] = useState({});
  const [error, setError] = useState("");
  if (!plan) return null;
  const p = (v) => money(v, currency);

  async function addAlert(key, alert) {
    setError("");
    try {
      // Kursmarken sind in der angezeigten Währung; weicht sie von der Handelswährung ab, mit dieser speichern
      const ccy = PRICE_KINDS.includes(alert.kind) && currency && currency !== nativeCurrency ? currency : "";
      await api.post("/alerts", { symbol, kind: alert.kind, params: alert.params, interval: alert.interval, once: alert.once, currency: ccy });
      setDone((d) => ({ ...d, [key]: true }));
    } catch (e) {
      setError(e.message);
    }
  }

  function AlertButton({ id, alert }) {
    if (!alert) return null;
    return done[id]
      ? <Link className="link small" to="/alerts">Alarm angelegt ✓</Link>
      : <button className="btn small" onClick={() => addAlert(id, alert)} title={alert.label}>Alarm: {alert.label}</button>;
  }

  return (
    <section className="panel span-all">
      <h2>{held ? "Nachkauf-Plan" : "Einstiegsplan"}</h2>
      {held && <p className="muted small">Du hast den Wert schon im Depot. Diese Marken eignen sich zum Aufstocken.</p>}
      <p className="entry-summary">{plan.summary}</p>
      {plan.setups.length > 0 && (
        <div className="setups">
          {plan.setups.map((s, i) => (
            <article key={s.title} className={`setup ${s.ok ? "" : "not-ok"} ${s.status === "now" ? "is-now" : ""}`}>
              <header>
                <span className={`chip kind-${s.kind}`}>{KIND_LABEL[s.kind] || s.kind}</span>
                <strong>{s.title}</strong>
                <span className={`chip ${s.status === "now" ? "ok" : ""}`}>{s.status === "now" ? "jetzt im Bereich" : `${s.distance_pct > 0 ? "+" : ""}${s.distance_pct.toLocaleString("de-DE")} % entfernt`}</span>
              </header>
              <div className="setup-levels">
                <span><span className="muted">{s.kind === "breakout" ? "Kauf ab" : "Einstieg"}</span> {s.kind === "breakout" ? p(s.entry) : `${p(s.zone[0])} – ${p(s.zone[1])}`}</span>
                <span><span className="muted">Stopp</span> {p(s.stop)}</span>
                {s.target && <span><span className="muted">Ziel</span> {p(s.target)}</span>}
                {s.crv && <span><span className="muted">CRV</span> {s.crv.toLocaleString("de-DE", { maximumFractionDigits: 1 })}</span>}
                {s.position && <span><span className="muted">Position</span> {s.position.shares} Stück ≈ {p(s.position.value)}</span>}
              </div>
              <p className="muted small">{s.why}</p>
              {s.problem && <p className="error small">{s.problem}</p>}
              <AlertButton id={`s${i}`} alert={s.alert} />
            </article>
          ))}
        </div>
      )}
      {plan.wait.length > 0 && (
        <>
          <h3 className="wait-title">Darauf warten</h3>
          <ul className="wait-list">
            {plan.wait.map((w, i) => (
              <li key={w.title}>
                <div>
                  <strong>{w.title}</strong>
                  <p className="muted small">{w.why}</p>
                </div>
                <AlertButton id={`w${i}`} alert={w.alert} />
              </li>
            ))}
          </ul>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      <p className="muted small">Alarme werden einmalig angelegt und melden sich per Push, wenn die Marke erreicht ist.</p>
    </section>
  );
}
