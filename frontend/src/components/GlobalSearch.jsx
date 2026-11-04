import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { displayTicker } from "../texts.js";

/** Suchfeld oben: Name, Kürzel oder ISIN eingeben, Treffer antippen, schon ist man auf der Seite des Werts. */
export default function GlobalSearch() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const box = useRef(null);
  const seq = useRef(0);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) { setRes(null); return undefined; }
    const id = setTimeout(async () => {
      const mine = ++seq.current;
      setLoading(true);
      try {
        const r = await api.get(`/search?q=${encodeURIComponent(term)}`);
        if (mine === seq.current) { setRes(r); setOpen(true); }
      } catch {
        if (mine === seq.current) setRes([]);
      } finally {
        if (mine === seq.current) setLoading(false);
      }
    }, 300);
    return () => clearTimeout(id);
  }, [q]);

  // Tastenkürzel am Laptop: „/“ springt in die Suche
  useEffect(() => {
    const onKey = (e) => {
      const tag = (e.target.tagName || "").toLowerCase();
      if (e.key === "/" && !["input", "textarea", "select"].includes(tag) && !e.target.isContentEditable) {
        e.preventDefault();
        box.current?.querySelector("input")?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const close = (e) => { if (!box.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);

  function go(symbol) {
    setOpen(false);
    setQ("");
    setRes(null);
    navigate(`/chart/${encodeURIComponent(symbol)}`);
  }

  const gtx = (res || []).filter((r) => r.exchange === "gettex");
  const other = (res || []).filter((r) => r.exchange !== "gettex");

  return (
    <div className="gsearch" ref={box}>
      <svg viewBox="0 0 24 24" className="gsearch-icon" aria-hidden="true"><path d="M11 4 A7 7 0 1 0 11.01 4 M16 16 L21 21" /></svg>
      <input type="search" value={q} onChange={(e) => setQ(e.target.value)} onFocus={() => res && setOpen(true)}
        placeholder="Aktie oder ETF suchen …" aria-label="Aktie oder ETF suchen"
        onKeyDown={(e) => { if (e.key === "Enter" && (gtx[0] || other[0])) go((gtx[0] || other[0]).symbol); if (e.key === "Escape") setOpen(false); }} />
      {loading ? <span className="spinner gsearch-spin" aria-hidden="true" /> : !q && <kbd className="gsearch-kbd" aria-hidden="true">/</kbd>}
      {open && res && (
        <div className="gsearch-pop" role="listbox">
          {!res.length && <p className="muted small">Nichts gefunden. Name, Kürzel oder ISIN versuchen.</p>}
          {gtx.length > 0 && <p className="gsearch-head">gettex <span className="chip ok">Standard</span></p>}
          {gtx.map((r) => <Hit key={r.symbol} r={r} onPick={go} />)}
          {other.length > 0 && <p className="gsearch-head">Andere Börsen</p>}
          {other.slice(0, 8).map((r) => <Hit key={r.symbol} r={r} onPick={go} />)}
        </div>
      )}
    </div>
  );
}

function Hit({ r, onPick }) {
  return (
    <button type="button" className="gsearch-hit" onClick={() => onPick(r.symbol)} role="option" aria-selected="false">
      <span className="gsearch-name">{r.name}</span>
      <span className="muted small">{displayTicker(r)} · {r.exchange}{r.currency ? ` · ${r.currency}` : ""}{r.type ? ` · ${r.type}` : ""}</span>
    </button>
  );
}
