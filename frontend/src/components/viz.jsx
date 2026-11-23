import { useId } from "react";
import { pct } from "../fmt.js";
import { SERIES } from "../theme.js";

/** Schlichte Kurslinie mit Fläche (SVG, skaliert mit der Breite). points: Zahlen oder {value}. */
export function LineArea({ values, height = 120, tone = null, showZero = false, labels = null }) {
  const id = useId().replace(/:/g, "");
  const v = (values || []).map((x) => (typeof x === "number" ? x : x?.value)).filter((x) => x != null && !Number.isNaN(x));
  if (v.length < 2) return <div className="muted small" style={{ height, display: "grid", placeItems: "center" }}>Noch zu wenig Verlauf</div>;
  const W = 600;
  const H = height;
  const min = Math.min(...v, showZero ? 0 : Infinity);
  const max = Math.max(...v, showZero ? 0 : -Infinity);
  const span = max - min || 1;
  const pad = 6;
  const pts = v.map((y, i) => [(i / (v.length - 1)) * W, pad + (1 - (y - min) / span) * (H - 2 * pad)]);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${W},${H} L0,${H} Z`;
  const up = tone ?? (v[v.length - 1] >= v[0] ? "pos" : "neg");
  const color = up === "pos" ? "var(--celeste)" : up === "neg" ? "var(--signal)" : "var(--accent)";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" width="100%" height={H} role="img"
      aria-label={labels ? `Verlauf von ${labels[0]} bis ${labels[1]}` : "Verlauf"} style={{ display: "block" }}>
      <defs>
        <linearGradient id={`g${id}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.18" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#g${id})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  );
}

/** Gestapelter Balken mit Legende (Aufteilung). items: [{label, value, pct}] */
export function Stack({ items, max = 7 }) {
  const top = items.slice(0, max);
  const rest = items.slice(max);
  const all = rest.length ? [...top, { label: "Weitere", pct: rest.reduce((a, b) => a + b.pct, 0), value: rest.reduce((a, b) => a + b.value, 0) }] : top;
  return (
    <>
      <div className="stack" role="img" aria-label={all.map((x) => `${x.label} ${pct(x.pct, 0).replace("+", "")}`).join(", ")}>
        {all.map((x, i) => <span key={x.label} style={{ width: `${x.pct}%`, background: SERIES[i % SERIES.length] }} title={`${x.label}: ${x.pct} %`} />)}
      </div>
      <ul className="stack-legend">
        {all.map((x, i) => (
          <li key={x.label}><i style={{ background: SERIES[i % SERIES.length] }} /><span className="lbl">{x.label}</span><span className="pct">{x.pct.toLocaleString("de-DE", { maximumFractionDigits: 1 })} %</span></li>
        ))}
      </ul>
    </>
  );
}

/** Halbkreis 0–100 (Fear & Greed). */
export function Gauge({ value, label, sub }) {
  const v = Math.max(0, Math.min(100, value ?? 50));
  const a = Math.PI * (1 - v / 100);
  const cx = 66, cy = 70, r = 56;
  const nx = cx + Math.cos(a) * (r - 10), ny = cy - Math.sin(a) * (r - 10);
  const seg = (from, to, color) => {
    const a1 = Math.PI * (1 - from / 100), a2 = Math.PI * (1 - to / 100);
    return <path d={`M${cx + Math.cos(a1) * r},${cy - Math.sin(a1) * r} A${r},${r} 0 0 1 ${cx + Math.cos(a2) * r},${cy - Math.sin(a2) * r}`}
      fill="none" stroke={color} strokeWidth="9" strokeLinecap="butt" />;
  };
  return (
    <div className="gauge">
      <svg viewBox="0 0 132 76" aria-hidden="true">
        {seg(0, 25, "rgba(var(--neg-rgb), 0.85)")}
        {seg(25.5, 45, "rgba(var(--neg-rgb), 0.4)")}
        {seg(45.5, 55, "var(--neutral)")}
        {seg(55.5, 75, "rgba(var(--pos-rgb), 0.45)")}
        {seg(75.5, 100, "rgba(var(--pos-rgb), 0.9)")}
        <line className="needle" x1={cx} y1={cy} x2={nx} y2={ny} />
        <circle cx={cx} cy={cy} r="4" fill="var(--chalk)" />
      </svg>
      <div>
        <div className="val">{value == null ? "–" : Math.round(value)}</div>
        <div><strong>{label || "–"}</strong></div>
        {sub && <div className="muted small">{sub}</div>}
      </div>
    </div>
  );
}

/** Wahrscheinlichkeiten fallen / seitwärts / steigen. */
export function ProbBar({ p, compact = false }) {
  if (!p) return null;
  const d = Math.round((p.p_down || 0) * 100), u = Math.round((p.p_up || 0) * 100);
  const f = Math.max(0, 100 - d - u);
  return (
    <div>
      <div className="pbar" role="img" aria-label={`fallen ${d} %, seitwärts ${f} %, steigen ${u} %`}>
        <span className="d" style={{ width: `${d}%` }} /><span className="f" style={{ width: `${f}%` }} /><span className="u" style={{ width: `${u}%` }} />
      </div>
      <div className="plegend">{compact
        ? <><span title="fallen">↓ {d} %</span><span title="seitwärts">→ {f} %</span><span title="steigen">↑ {u} %</span></>
        : <><span>fallen {d} %</span><span>seitwärts {f} %</span><span>steigen {u} %</span></>}</div>
    </div>
  );
}

/** Beitrag einer Datengruppe (−…+) als Balken um die Mitte. */
export function DriverBar({ delta }) {
  const w = Math.min(50, Math.abs(delta) * 120);
  const style = delta >= 0
    ? { left: "50%", width: `${w}%`, background: "var(--celeste)" }
    : { right: "50%", width: `${w}%`, background: "var(--signal)" };
  return <span className="dbar"><span style={style} /></span>;
}

export function Spark({ values, width = 110, height = 30 }) {
  const v = (values || []).filter((x) => x != null);
  if (v.length < 2) return null;
  const min = Math.min(...v), max = Math.max(...v), span = max - min || 1;
  const pts = v.map((y, i) => `${((i / (v.length - 1)) * width).toFixed(1)},${(height - 2 - ((y - min) / span) * (height - 4)).toFixed(1)}`).join(" ");
  const up = v[v.length - 1] >= v[0];
  return (
    <svg className={`spark ${up ? "pos" : "neg"}`} width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-hidden="true">
      <polyline points={pts} fill="none" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
