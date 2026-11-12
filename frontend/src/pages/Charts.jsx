import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import SymbolSearch from "../components/SymbolSearch.jsx";
import { CHART_TYPES } from "../components/PriceChart.jsx";
import WorkspaceChart from "../components/WorkspaceChart.jsx";
import { Empty, ErrorText, Loading } from "../components/ui.jsx";
import { dateTime, money } from "../fmt.js";
import { indicatorTitle, INDICATORS, PARAM_LABEL } from "../indicators.js";
import { displayName, displayTicker } from "../texts.js";
import Icon from "../components/Icon.jsx";
import { INTRADAY, intervalsFor, PERIOD_LABEL, periodsFor, pickPeriod } from "../intervals.js";

const RANGES = [
  { id: "1d", label: "1 T", period: "1d", interval: "5m" },
  { id: "5d", label: "1 W", period: "5d", interval: "15m" },
  { id: "1mo", label: "1 M", period: "1mo", interval: "1d" },
  { id: "3mo", label: "3 M", period: "3mo", interval: "1d" },
  { id: "6mo", label: "6 M", period: "6mo", interval: "1d" },
  { id: "1y", label: "1 J", period: "1y", interval: "1d" },
  { id: "2y", label: "2 J", period: "2y", interval: "1d" },
  { id: "5y", label: "5 J", period: "5y", interval: "1wk" },
];
const TOOLS = [
  { id: null, label: "Bewegen", short: "Bewegen", icon: "✋", help: "Chart verschieben und zoomen" },
  { id: "hline", label: "Waagrechte Linie", short: "Linie", icon: "—", help: "Antippen setzt die Linie – beim Ziehen wandert sie mit" },
  { id: "trend", label: "Trendlinie", short: "Trend", icon: "╱", help: "Vom Anfang zum Ende ziehen – oder beide Punkte antippen" },
  { id: "ray", label: "Strahl", short: "Strahl", icon: "↗", help: "Wie Trendlinie, aber bis heute verlängert" },
  { id: "fib", label: "Fibonacci", short: "Fibo", icon: "≡", help: "Vom Tief zum Hoch ziehen – zeigt typische Rücksetzer-Marken" },
];
const MAGNET_KEY = "tradehelper_chart_magnet";
const PALETTE = ["#f2b84b", "#6fd3c3", "#7aa7ff", "#c792ea", "#ff9f6b", "#ff6b6b", "#e6edf3"];
const uid = () => Math.random().toString(36).slice(2, 10);
const fmtP = (v) => (v == null ? "" : Number(v).toLocaleString("de-DE", { maximumFractionDigits: v < 10 ? 4 : 2 }));

function Picker() {
  const navigate = useNavigate();
  const [list, setList] = useState(null);
  const [saved, setSaved] = useState([]);
  useEffect(() => {
    api.get("/watchlist").then(setList).catch(() => setList([]));
    api.get("/charts").then(setSaved).catch(() => {});
  }, []);
  const savedSet = new Set(saved.map((s) => s.symbol));
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Charts</h1>
          <p className="muted">Dein Arbeitsplatz: Linien einzeichnen, Kennlinien dazunehmen, alles wird pro Wert gespeichert.</p>
        </div>
      </div>
      <section className="panel">
        <h2>Wert wählen</h2>
        {!list && <Loading />}
        {list && (
          <div className="chip-grid">
            {list.map((w) => (
              <Link key={w.symbol} to={`/charts/${encodeURIComponent(w.symbol)}`} className="pick-chip">
                <strong>{displayName(w)}</strong>
                <span className="muted small">{displayTicker(w)}{savedSet.has(w.symbol) ? " · ✏️ bearbeitet" : ""}</span>
              </Link>
            ))}
          </div>
        )}
        <h3 className="sub-title">Anderen Wert suchen</h3>
        <SymbolSearch onPick={(r) => navigate(`/charts/${encodeURIComponent(r.symbol)}`)} actionLabel="Öffnen" />
      </section>
    </>
  );
}

export default function Charts() {
  const { symbol: raw } = useParams();
  const symbol = raw ? decodeURIComponent(raw).toUpperCase() : null;
  return symbol ? <Workspace key={symbol} symbol={symbol} /> : <Picker />;
}

function Workspace({ symbol }) {
  const [layout, setLayout] = useState(null);
  const [rows, setRows] = useState(null);
  const [meta, setMeta] = useState(null);
  const [positions, setPositions] = useState([]);
  const [error, setError] = useState("");
  const [tool, setTool] = useState(null);
  const [pending, setPending] = useState(null);
  const [selected, setSelected] = useState(null);
  const [saveState, setSaveState] = useState("");
  const [addKind, setAddKind] = useState("");
  const [msg, setMsg] = useState("");
  const dirty = useRef(false);

  useEffect(() => {
    api.get(`/charts/${encodeURIComponent(symbol)}`).then((l) => { setLayout(l); dirty.current = false; })
      .catch((e) => setError(e.message));
  }, [symbol]);

  const period = layout?.period || "6mo";
  const interval = layout?.interval || "1d";
  useEffect(() => {
    if (!layout) return;
    setRows(null);
    api.get(`/history/${encodeURIComponent(symbol)}?period=${period}&interval=${interval}`)
      .then((r) => { setRows(r.rows); setMeta(r.meta || r); setPositions(r.positions || []); setError(""); })
      .catch((e) => setError(e.message));
  }, [symbol, period, interval, !!layout]); // eslint-disable-line react-hooks/exhaustive-deps

  // Automatisch speichern, kurz nach der letzten Änderung
  useEffect(() => {
    if (!layout || !dirty.current) return undefined;
    setSaveState("…");
    const t = setTimeout(async () => {
      try {
        const { updated_at: _u, ...body } = layout;
        await api.put(`/charts/${encodeURIComponent(symbol)}`, body);
        setSaveState("gespeichert");
      } catch (e) {
        setSaveState("");
        setError(e.message);
      }
    }, 700);
    return () => clearTimeout(t);
  }, [layout, symbol]);

  const update = useCallback((fn) => { dirty.current = true; setLayout((l) => ({ ...l, ...fn(l) })); }, []);

  const [magnet, setMagnet] = useState(() => {
    try { return localStorage.getItem(MAGNET_KEY) !== "0"; } catch { return true; }
  });
  const toggleMagnet = () => setMagnet((m) => {
    try { localStorage.setItem(MAGNET_KEY, m ? "0" : "1"); } catch { /* egal */ }
    return !m;
  });

  const onDraw = useCallback((kind, points, { touch } = {}) => {
    const d = { id: uid(), kind, points, color: kind === "fib" ? "#7aa7ff" : PALETTE[0], label: "" };
    update((l) => ({ drawings: [...l.drawings, d] }));
    setSelected(d.id);
    setPending(null);
    // Auf dem Handy nach jeder Zeichnung zurück zum Verschieben – sonst wischt man versehentlich neue Linien
    if (touch) setTool(null);
  }, [update]);

  function pickTool(id) {
    setTool(id);
    setPending(null);
  }

  function undo() {
    const last = drawings[drawings.length - 1];
    if (!last) return;
    removeDrawing(last.id);
    if (selected === last.id) setSelected(null);
  }

  function addIndicator(kind) {
    if (!kind) return;
    const def = INDICATORS[kind];
    const used = new Set(layout.indicators.map((i) => i.color));
    const color = PALETTE.find((c) => !used.has(c)) || PALETTE[0];
    update((l) => ({ indicators: [...l.indicators, { id: uid(), kind, params: { ...def.params }, color }] }));
    setAddKind("");
  }

  const setInd = (id, patch) => update((l) => ({ indicators: l.indicators.map((i) => (i.id === id ? { ...i, ...patch } : i)) }));
  const setDrawing = (id, patch) => update((l) => ({ drawings: l.drawings.map((d) => (d.id === id ? { ...d, ...patch } : d)) }));
  const removeDrawing = (id) => { update((l) => ({ drawings: l.drawings.filter((d) => d.id !== id) })); if (selected === id) setSelected(null); };

  async function alarmAt(d) {
    const last = rows?.[rows.length - 1]?.close;
    const value = d.points[0].price;
    const kind = last != null && value < last ? "price_below" : "price_above";
    try {
      await api.post("/alerts", { symbol, kind, params: { value: Math.round(value * 10000) / 10000 }, interval: "1d", once: true,
        currency: meta?.currency && meta.currency !== meta.native_currency ? meta.currency : "" });
      setMsg(`Alarm angelegt: ${kind === "price_below" ? "fällt unter" : "steigt über"} ${money(value, meta?.currency)}.`);
    } catch (e) { setError(e.message); }
  }

  const rangeId = RANGES.find((r) => r.period === period && r.interval === interval)?.id;
  const ivMeta = { intraday_limit: symbol?.endsWith(".GTX") ? "5d" : null };
  const intraday = interval === "1s" ? "seconds" : INTRADAY.has(interval);
  const help = TOOLS.find((t) => t.id === tool)?.help;
  const drawings = layout?.drawings || [];
  const sel = drawings.find((d) => d.id === selected);
  const indicators = useMemo(() => layout?.indicators || [], [layout?.indicators]);
  const name = meta?.name || symbol.replace(/\.GTX$/, "");

  if (error && !layout) return <ErrorText error={error} />;
  if (!layout) return <Loading />;

  return (
    <>
      <div className="page-head ws-head">
        <div>
          <Link to="/charts" className="muted small">← Charts</Link>
          <h1>{name}</h1>
          <p className="muted small">{meta?.ticker || symbol}{meta?.exchange ? ` · ${meta.exchange}` : ""}{meta?.currency ? ` · ${meta.currency}` : ""}
            {" · "}<Link to={`/chart/${encodeURIComponent(symbol)}`}>Einschätzung ansehen</Link></p>
        </div>
        <span className="muted small save-state" aria-live="polite">{saveState}{layout.updated_at && !saveState ? `zuletzt geändert ${dateTime(layout.updated_at)}` : ""}</span>
      </div>

      <div className="ws-toolbar">
        <div className="seg" role="tablist" aria-label="Zeitraum">
          {RANGES.map((r) => (
            <button key={r.id} className={rangeId === r.id ? "on" : ""} onClick={() => update(() => ({ period: r.period, interval: r.interval }))}>{r.label}</button>
          ))}
        </div>
        <div className="seg seg-iv" role="group" aria-label="Kerzenlänge">
          {intervalsFor(ivMeta).map((iv) => (
            <button key={iv.id} className={iv.id === interval ? "on" : ""} title={iv.title}
              onClick={() => update(() => ({ interval: iv.id, period: pickPeriod(iv.id, period, ivMeta) }))}>{iv.label}</button>
          ))}
        </div>
        {!rangeId && (
          <select value={period} onChange={(e) => update(() => ({ period: e.target.value }))} aria-label="Zeitraum">
            {periodsFor(interval, ivMeta).map((x) => <option key={x} value={x}>{PERIOD_LABEL[x]}</option>)}
          </select>
        )}
        <select value={layout.type} onChange={(e) => update(() => ({ type: e.target.value }))} aria-label="Darstellung">
          {CHART_TYPES.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
        </select>
        <select value={addKind} onChange={(e) => addIndicator(e.target.value)} aria-label="Kennlinie hinzufügen">
          <option value="">+ Kennlinie …</option>
          {Object.entries(INDICATORS).map(([k, d]) => <option key={k} value={k}>{d.label}</option>)}
        </select>
      </div>
      <div className="ws-tools" role="toolbar" aria-label="Zeichenwerkzeuge">
        {TOOLS.map((t) => (
          <button key={t.label} className={`tool ${tool === t.id ? "on" : ""}`} onClick={() => pickTool(t.id)} title={t.help} aria-pressed={tool === t.id} aria-label={t.label}>
            <span aria-hidden="true">{t.icon}</span> <em className="tool-long">{t.label}</em><em className="tool-short">{t.short}</em>
          </button>
        ))}
        <span className="ws-tools-gap" />
        <button className={`tool ${magnet ? "on" : ""}`} onClick={toggleMagnet} aria-pressed={magnet}
          title="Magnet: Punkte rasten an Eröffnung, Hoch, Tief oder Schluss der Kerze ein">
          <span aria-hidden="true">🧲</span> <em className="tool-long">Magnet</em><em className="tool-short">Magnet</em>
        </button>
        <button className="tool" onClick={undo} disabled={!drawings.length} title="Letzte Zeichnung entfernen" aria-label="Rückgängig">
          <span aria-hidden="true">↶</span> <em className="tool-long">Rückgängig</em><em className="tool-short">Zurück</em>
        </button>
      </div>
      {msg && <p className="ok small" role="status">{msg}</p>}
      <ErrorText error={layout && error} />

      <section className="panel chart-panel ws-panel">
        {tool && (
          <p className="ws-help small" role="status">
            {pending ? "Jetzt den zweiten Punkt antippen." : help} <button className="link small" onClick={() => pickTool(null)}>Fertig</button>
          </p>
        )}
        {!rows ? <Loading text="Lade Kurse …" /> : (
          <WorkspaceChart rows={rows} type={layout.type} intraday={intraday} indicators={indicators} drawings={drawings}
            tool={tool} pending={pending} selected={selected} onPending={setPending} onDraw={onDraw} magnet={magnet}
            positions={positions} currency={meta?.currency} />
        )}
        {sel && !tool && (
          <div className="ws-selbar" role="group" aria-label="Ausgewählte Zeichnung">
            <strong>{TOOLS.find((t) => t.id === sel.kind)?.label}</strong>
            <span className="muted small">{sel.kind === "hline" ? fmtP(sel.points[0].price) : `${fmtP(sel.points[0].price)} → ${fmtP(sel.points[1]?.price)}`}</span>
            <span className="ws-swatches">
              {PALETTE.map((c) => (
                <button key={c} className={`swatch ${sel.color === c ? "on" : ""}`} style={{ background: c }} onClick={() => setDrawing(sel.id, { color: c })} aria-label={`Farbe ${c}`} />
              ))}
            </span>
            {sel.kind === "hline" && <button className="btn small" onClick={() => alarmAt(sel)}><Icon name="bell" /> Alarm</button>}
            <button className="btn small danger" onClick={() => removeDrawing(sel.id)}>Löschen</button>
            <button className="icon-btn" onClick={() => setSelected(null)} aria-label="Auswahl schließen">✕</button>
          </div>
        )}
      </section>

      <div className="ws-lists">
        <section className="panel">
          <h2><Icon name="activity" className="h-icon" /> Kennlinien</h2>
          {!indicators.length && <p className="muted small">Noch keine. Oben „+ Kennlinie“ wählen.</p>}
          <ul className="ws-list">
            {indicators.map((ind) => (
              <li key={ind.id}>
                <input type="color" value={ind.color} onChange={(e) => setInd(ind.id, { color: e.target.value })} aria-label="Farbe" />
                <span className="ws-item-title" title={INDICATORS[ind.kind]?.explain}>{indicatorTitle(ind)}</span>
                {Object.entries(ind.params || {}).map(([k, v]) => (
                  <label key={k} className="ws-param">{PARAM_LABEL[k] || k}
                    <input inputMode="decimal" value={v} onChange={(e) => {
                      const n = Number(String(e.target.value).replace(",", "."));
                      if (Number.isFinite(n) && n > 0 && n <= 500) setInd(ind.id, { params: { ...ind.params, [k]: n } });
                    }} />
                  </label>
                ))}
                <button className="link danger small" onClick={() => update((l) => ({ indicators: l.indicators.filter((i) => i.id !== ind.id) }))}>Entfernen</button>
              </li>
            ))}
          </ul>
        </section>
        <section className="panel">
          <h2><Icon name="pencil" className="h-icon" /> Zeichnungen</h2>
          {!drawings.length && <p className="muted small">Noch keine. Werkzeug wählen und in den Chart tippen oder ziehen.</p>}
          <ul className="ws-list">
            {drawings.map((d) => (
              <li key={d.id} className={selected === d.id ? "sel" : ""} onClick={() => setSelected(d.id)}>
                <input type="color" value={d.color} onChange={(e) => setDrawing(d.id, { color: e.target.value })} aria-label="Farbe" />
                <span className="ws-item-title">{TOOLS.find((t) => t.id === d.kind)?.label}</span>
                <input className="ws-label" placeholder="Beschriftung" value={d.label} maxLength={60}
                  onChange={(e) => setDrawing(d.id, { label: e.target.value })} />
                {d.kind === "hline" ? (
                  <label className="ws-param">bei
                    <input inputMode="decimal" defaultValue={fmtP(d.points[0].price)} onBlur={(e) => {
                      const n = Number(String(e.target.value).replace(/\./g, "").replace(",", "."));
                      if (Number.isFinite(n) && n > 0) setDrawing(d.id, { points: [{ ...d.points[0], price: n }] });
                    }} />
                  </label>
                ) : (
                  <span className="muted small">{fmtP(d.points[0].price)} → {fmtP(d.points[1]?.price)}</span>
                )}
                {d.kind === "hline" && <button className="link small" onClick={() => alarmAt(d)}>Alarm</button>}
                <button className="link danger small" onClick={(e) => { e.stopPropagation(); removeDrawing(d.id); }}>Löschen</button>
              </li>
            ))}
          </ul>
          {drawings.length > 0 && (
            <button className="link danger small" onClick={() => { if (window.confirm("Alle Zeichnungen dieses Werts löschen?")) update(() => ({ drawings: [] })); }}>Alle löschen</button>
          )}
        </section>
      </div>
      {!rows && error && <Empty title="Keine Kurse"><p className="muted">{error}</p></Empty>}
    </>
  );
}
