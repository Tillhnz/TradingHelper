import { money } from "../fmt.js";
import { ACTION_UI, HELD_UI } from "../texts.js";
import Term from "./Term.jsx";
import { standLabel } from "../cache.js";

export function Loading({ text = "Lade …" }) {
  return <p className="muted loading" role="status"><span className="spinner" aria-hidden="true" />{text}</p>;
}

/** Kleiner Hinweis unter der Überschrift: „aktualisiere …“ bzw. „Stand 18:42“ (für useCachedGet). */
export function RefreshState({ q }) {
  if (!q || q.data == null) return null;
  if (q.refreshing) return <span className="refresh-state"><span className="spinner" aria-hidden="true" /> aktualisiere …</span>;
  if (q.refreshError) return <span className="refresh-state warn" title={q.refreshError}>{standLabel(q.at)} · Aktualisieren klappt gerade nicht</span>;
  return null;
}

export function ErrorText({ error }) {
  if (!error) return null;
  return <p className="error" role="alert">{error}</p>;
}

/** Einschätzung in Alltagssprache („Gute Gelegenheit“, „Abwarten“, „Vorsicht“); bei Bestand aus Haltersicht. */
export function ActionBadge({ action, held = false, large = false }) {
  if (!action) return null;
  const ui = ACTION_UI[action];
  const label = held ? HELD_UI[action]?.label : ui?.label;
  return (
    <span className={`badge ${ui?.tone || ""} ${large ? "large" : ""}`} title={`Regel-Einschätzung: ${action}`}>
      <span className="badge-icon" aria-hidden="true">{ui?.icon}</span>{label || action}
    </span>
  );
}

/** Kleine Kurslinie der letzten Tage, Farbe nach Gesamtrichtung. */
export function Sparkline({ values, width = 96, height = 28 }) {
  if (!values || values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values
    .map((v, i) => `${((i / (values.length - 1)) * width).toFixed(1)},${(height - ((v - min) / span) * (height - 4) - 2).toFixed(1)}`)
    .join(" ");
  const up = values[values.length - 1] >= values[0];
  return (
    <svg className={`spark ${up ? "pos" : "neg"}`} width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <polyline points={pts} fill="none" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export function Stat({ label, value, className = "", term }) {
  return (
    <div className={`stat ${className}`}>
      <span className="stat-label">{term ? <Term name={term}>{label}</Term> : label}</span>
      <strong className="stat-value">{value}</strong>
    </div>
  );
}

export function Empty({ title, children }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {children}
    </div>
  );
}

/** Stopp, Ziel und Chance/Risiko einer Empfehlung. */
export function Levels({ rec, currency }) {
  if (!rec.stop && !rec.target) return null;
  return (
    <div className="levels small">
      {rec.stop && <span><span className="muted"><Term name="Stopp" /></span> {money(rec.stop, currency)}</span>}
      {rec.target && <span><span className="muted"><Term name="Ziel" /></span> {money(rec.target, currency)}</span>}
      {rec.crv && <span><span className="muted"><Term name="Chance/Risiko" /></span> {rec.crv.toLocaleString("de-DE", { maximumFractionDigits: 1 })}</span>}
      {rec.position && (
        <span className="levels-pos">
          <span className="muted">Vorschlag</span> {rec.position.shares} Stück ≈ {money(rec.position.value, currency)}
          <span className="muted"> · Risiko {money(rec.position.risk, currency)} ({rec.position.risk_pct.toLocaleString("de-DE")} % vom Depot)</span>
        </span>
      )}
    </div>
  );
}
