import { ACTION_TONE } from "../fmt.js";

export function Loading({ text = "Lade …" }) {
  return <p className="muted loading" role="status"><span className="spinner" aria-hidden="true" />{text}</p>;
}

export function ErrorText({ error }) {
  if (!error) return null;
  return <p className="error" role="alert">{error}</p>;
}

export function ActionBadge({ action }) {
  if (!action) return null;
  return <span className={`badge ${ACTION_TONE[action] || ""}`}>{action}</span>;
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

export function Stat({ label, value, className = "" }) {
  return (
    <div className={`stat ${className}`}>
      <span className="stat-label">{label}</span>
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
