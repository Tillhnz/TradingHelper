import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { useCachedGet } from "../cache.js";
import Icon from "../components/Icon.jsx";
import Modal from "../components/Modal.jsx";
import ReportModal from "../components/ReportModal.jsx";
import { RefreshState } from "../components/ui.jsx";
import { hasPending } from "./Watchlist.jsx";
import { DEFAULT_WIDGETS, parseLayout, WIDGETS } from "../widgets/index.jsx";

const SIZE_LABEL = { s: "S", m: "M", l: "L", xl: "Breit" };
const uid = () => Math.random().toString(36).slice(2, 9);

function AddDialog({ layout, onAdd, onClose }) {
  const [chartFor, setChartFor] = useState(false);
  const [q, setQ] = useState("");
  const [hits, setHits] = useState([]);
  const [period, setPeriod] = useState("6mo");
  const used = new Set(layout.widgets.map((w) => w.type));
  useEffect(() => {
    if (!chartFor || q.trim().length < 2) { setHits([]); return undefined; }
    const id = setTimeout(() => api.get(`/search?q=${encodeURIComponent(q.trim())}`).then((r) => setHits(r.slice(0, 8))).catch(() => setHits([])), 250);
    return () => clearTimeout(id);
  }, [q, chartFor]);
  return (
    <Modal title={chartFor ? "Mini-Chart: welcher Wert?" : "Baustein hinzufügen"} onClose={onClose} wide>
      {!chartFor ? (
        <div className="gallery">
          {Object.entries(WIDGETS).map(([type, w]) => (
            <button key={type} disabled={!w.multi && used.has(type)}
              onClick={() => (type === "chart" ? setChartFor(true) : onAdd({ id: uid(), type, size: w.sizes.includes("m") ? "m" : w.sizes[0] }))}>
              <Icon name={w.icon} /><strong>{w.label}</strong><span className="muted small">{w.text}</span>
              {!w.multi && used.has(type) && <span className="muted small">schon auf der Startseite</span>}
            </button>
          ))}
        </div>
      ) : (
        <>
          <label>Wert suchen<input value={q} onChange={(e) => setQ(e.target.value)} placeholder="z. B. SAP, MSCI World, Bitcoin" autoFocus /></label>
          <div className="seg" style={{ margin: "0.75rem 0" }}>
            {[["1mo", "1 M"], ["3mo", "3 M"], ["6mo", "6 M"], ["1y", "1 J"], ["5y", "5 J"]].map(([k, l]) => (
              <button key={k} className={period === k ? "on" : ""} onClick={() => setPeriod(k)}>{l}</button>
            ))}
          </div>
          <ul className="mini-list">
            {hits.map((h) => (
              <li key={h.symbol}>
                <span className="two"><span className="nm">{h.name}</span><span className="sub">{h.exchange} · {h.symbol}</span></span>
                <button className="btn small" onClick={() => onAdd({ id: uid(), type: "chart", size: "m", config: { symbol: h.symbol, period } })}>Hinzufügen</button>
              </li>
            ))}
          </ul>
          <div className="actions"><button className="btn" onClick={() => setChartFor(false)}>Zurück</button></div>
        </>
      )}
    </Modal>
  );
}

/** Startseite aus frei anordenbaren Bausteinen. „Anpassen“: hinzufügen, verschieben (ziehen oder Pfeile), Größe, entfernen. */
export default function Home({ user }) {
  const settingsQ = useCachedGet("/settings");
  const overview = useCachedGet("/watchlist/overview", { pollWhile: hasPending });
  const portfolioQ = useCachedGet("/portfolio");
  const saved = settingsQ.data?.fields?.home_layout?.value;
  const [draft, setDraft] = useState(null);
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [drag, setDrag] = useState(null);
  const [over, setOver] = useState(null);
  const dragRef = useRef(null);
  const [params, setParams] = useSearchParams();
  const [report, setReport] = useState(() => params.get("bericht"));

  const layout = useMemo(() => draft || parseLayout(saved), [draft, saved]);
  const editing = !!draft;
  const shared = { rows: overview.data, portfolio: portfolioQ.data, settings: settingsQ.data, priv: layout.private };

  function update(fn) { setDraft((d) => fn(d || parseLayout(saved))); }
  const move = (i, d) => update((l) => {
    const w = [...l.widgets];
    const j = i + d;
    if (j < 0 || j >= w.length) return l;
    [w[i], w[j]] = [w[j], w[i]];
    return { ...l, widgets: w };
  });
  const resize = (id, size) => update((l) => ({ ...l, widgets: l.widgets.map((w) => (w.id === id ? { ...w, size } : w)) }));
  const remove = (id) => update((l) => ({ ...l, widgets: l.widgets.filter((w) => w.id !== id) }));
  const add = (w) => { update((l) => ({ ...l, widgets: [...l.widgets, w] })); setAdding(false); };
  function dropOn(targetId) {
    const from = dragRef.current;
    setDrag(null); setOver(null); dragRef.current = null;
    if (!from || from === targetId) return;
    update((l) => {
      const w = [...l.widgets];
      const a = w.findIndex((x) => x.id === from);
      const [item] = w.splice(a, 1);
      const b = targetId == null ? w.length : w.findIndex((x) => x.id === targetId);
      w.splice(b, 0, item);
      return { ...l, widgets: w };
    });
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      const value = JSON.stringify({ v: 2, widgets: layout.widgets, private: layout.private });
      const r = await api.put("/settings", { home_layout: value });
      settingsQ.set(r);
      setDraft(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  const closeReport = () => {
    setReport(null);
    if (params.get("bericht")) { params.delete("bericht"); setParams(params, { replace: true }); }
  };

  return (
    <div className={editing ? "home-edit" : ""}>
      {editing ? (
        <div className="editbar">
          <strong>Startseite anpassen</strong>
          <span className="muted small grow">Bausteine ziehen oder mit den Pfeilen verschieben, Größe wählen, ✕ entfernt.</span>
          <label className="check" style={{ fontWeight: 400 }}>
            <input type="checkbox" checked={layout.private} onChange={(e) => update((l) => ({ ...l, private: e.target.checked }))} />
            Beträge verbergen
          </label>
          <button className="btn" onClick={() => setAdding(true)}><Icon name="plus" /> Baustein</button>
          <button className="btn" onClick={() => setDraft({ widgets: DEFAULT_WIDGETS, private: layout.private })}>Standard</button>
          <button className="btn" onClick={() => setDraft(null)}>Abbrechen</button>
          <button className="btn primary" onClick={save} disabled={saving}><Icon name="check" /> {saving ? "Speichere …" : "Fertig"}</button>
        </div>
      ) : (
        <div className="actions" style={{ justifyContent: "flex-end", marginTop: 0, marginBottom: "0.25rem" }}>
          <RefreshState q={overview} />
          <button className="btn ghost" onClick={() => setReport("latest")}><Icon name="report" /> Bericht</button>
          <button className="btn ghost" onClick={() => setDraft(parseLayout(saved))}><Icon name="grid" /> Anpassen</button>
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}

      <div className="wgrid" onDragOver={(e) => { if (editing) e.preventDefault(); }} onDrop={() => editing && over == null && dropOn(null)}>
        {layout.widgets.map((w, i) => {
          const def = WIDGETS[w.type];
          if (!def) return null;
          const C = def.C;
          return (
            <div key={w.id} className={`w ${w.size} ${drag === w.id ? "dragging" : ""} ${over === w.id && drag !== w.id ? "drop-before" : ""}`}
              draggable={editing} onDragStart={(e) => { dragRef.current = w.id; setDrag(w.id); e.dataTransfer.effectAllowed = "move"; }}
              onDragOver={(e) => { if (editing) { e.preventDefault(); e.stopPropagation(); setOver(w.id); } }}
              onDragLeave={() => setOver((o) => (o === w.id ? null : o))}
              onDrop={(e) => { e.preventDefault(); e.stopPropagation(); dropOn(w.id); }}
              onDragEnd={() => { setDrag(null); setOver(null); }}>
              {editing && (
                <div className="wedit">
                  <span className="grip" title="Ziehen zum Verschieben"><Icon name="grip" /></span>
                  <button onClick={() => move(i, -1)} aria-label="Nach vorne" disabled={i === 0}>←</button>
                  <button onClick={() => move(i, 1)} aria-label="Nach hinten" disabled={i === layout.widgets.length - 1}>→</button>
                  {def.sizes.map((s) => <button key={s} className={w.size === s ? "on" : ""} onClick={() => resize(w.id, s)}>{SIZE_LABEL[s]}</button>)}
                  <button onClick={() => remove(w.id)} aria-label={`${def.label} entfernen`}>✕</button>
                </div>
              )}
              {editing && def.bare ? <div className="wcard"><span className="wtitle"><Icon name={def.icon} />{def.label}</span><C shared={shared} config={w.config} size={w.size} user={user} /></div>
                : <C shared={shared} config={w.config} size={w.size} user={user} />}
            </div>
          );
        })}
      </div>
      {editing && (
        <div className="actions" style={{ justifyContent: "center", marginTop: "1.5rem" }}>
          <button className="btn" onClick={() => setAdding(true)}><Icon name="plus" /> Baustein hinzufügen</button>
        </div>
      )}
      {adding && <AddDialog layout={layout} onAdd={add} onClose={() => setAdding(false)} />}
      {report && <ReportModal id={report === "latest" ? null : report} onClose={closeReport} />}
    </div>
  );
}
