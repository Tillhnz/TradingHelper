import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { displayTicker } from "../texts.js";

/**
 * Suche nach Name, Symbol oder ISIN. Zeigt jeden Börsenplatz einzeln mit Währung, damit man z. B.
 * Apple an der Nasdaq (USD) oder an Xetra (EUR) auswählen kann.
 */
export default function SymbolSearch({ onPick, actionLabel = "Hinzufügen", busySymbol = null, exclude = [] }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) { setResults(null); setError(""); return undefined; }
    const id = setTimeout(async () => {
      const mine = ++seq.current;
      setLoading(true);
      try {
        const r = await api.get(`/search?q=${encodeURIComponent(term)}`);
        if (mine === seq.current) { setResults(r); setError(""); }
      } catch (e) {
        if (mine === seq.current) setError(e.message);
      } finally {
        if (mine === seq.current) setLoading(false);
      }
    }, 350);
    return () => clearTimeout(id);
  }, [q]);

  const direct = q.trim().toUpperCase();
  const showDirect = direct.length >= 1 && /^[A-Z0-9.^=\-]+$/.test(direct) && !(results || []).some((r) => r.symbol === direct);

  function submit(e) {
    e.preventDefault();
    if (results?.length === 1) onPick(results[0]);
    else if (showDirect) onPick({ symbol: direct });
  }

  return (
    <div className="search">
      <form onSubmit={submit}>
        <label>
          Wert hinzufügen <span className="hint">Name, Kürzel oder ISIN, z. B. „Apple“, „SAP“, „MSCI World“</span>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Suchen …" autoComplete="off" />
        </label>
      </form>
      {loading && <p className="muted small">Suche …</p>}
      {error && <p className="error small">{error}</p>}
      {results && (
        <ul className="search-results">
          {results.map((r, i) => {
            const added = exclude.includes(r.symbol);
            const firstOther = r.exchange !== "gettex" && (i === 0 || results[i - 1].exchange === "gettex");
            return (
              <li key={r.symbol} className={firstOther && i > 0 ? "sr-sep" : ""}>
                <div className="sr-main">
                  <strong className="sr-title">{r.name}</strong>
                  <span className="sr-name">{displayTicker(r)}{r.isin && r.ticker ? ` · ${r.isin}` : ""}</span>
                </div>
                <div className="sr-meta">
                  <span className={`chip ${r.exchange === "gettex" ? "ok" : ""}`}>{r.exchange || "?"}{r.exchange === "gettex" ? " · Standard" : ""}</span>
                  {r.currency && <span className="chip ccy">{r.currency}</span>}
                  <span className="muted small hide-sm">{r.type}</span>
                </div>
                <button className="btn small" disabled={added || busySymbol === r.symbol} onClick={() => onPick(r)}>
                  {added ? "Vorhanden" : busySymbol === r.symbol ? "…" : actionLabel}
                </button>
              </li>
            );
          })}
          {!results.length && <li className="muted">Nichts gefunden.</li>}
          {showDirect && (
            <li className="sr-direct">
              <span className="muted small">Symbol direkt verwenden:</span> <strong className="sym">{direct}</strong>
              <button className="btn small" disabled={exclude.includes(direct) || busySymbol === direct} onClick={() => onPick({ symbol: direct })}>{actionLabel}</button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
