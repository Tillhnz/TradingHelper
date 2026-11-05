import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import BuyDialog from "../components/BuyDialog.jsx";
import SymbolSearch from "../components/SymbolSearch.jsx";
import { ActionBadge, Empty, ErrorText, Loading, Sparkline } from "../components/ui.jsx";
import { money, num, pct, signedMoney, tone } from "../fmt.js";
import { useLiveQuotes } from "../live.js";
import { useMode } from "../mode.js";
import { displayName, displayTicker } from "../texts.js";

const FILTERS = [
  { id: "all", label: "Alle" },
  { id: "held", label: "Im Depot" },
  { id: "watch", label: "Beobachtet" },
  { id: "chance", label: "Gelegenheiten" },
];

export default function Watchlist() {
  const { mode } = useMode();
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState("");
  const [buying, setBuying] = useState(null);
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState("all");

  const load = useCallback(async () => {
    try {
      setRows(await api.get("/watchlist/overview"));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function add(r) {
    setBusy(r.symbol);
    setError("");
    setMsg("");
    try {
      const info = await api.post("/watchlist", { symbol: r.symbol });
      setMsg(`${info.name || info.added} wird jetzt beobachtet${info.exchange ? ` (${info.exchange})` : ""}.`);
      setAdding(false);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  }

  async function remove(r) {
    if (!window.confirm(`${displayName(r)} nicht mehr beobachten?`)) return;
    try {
      await api.del(`/watchlist/${encodeURIComponent(r.symbol)}`);
      setRows((rs) => rs.filter((x) => x.symbol !== r.symbol));
    } catch (e) {
      setError(e.message);
    }
  }

  const quotes = useLiveQuotes((rows || []).map((r) => r.symbol));
  const shown = (rows || []).filter((r) => (filter === "held" ? r.holding : filter === "watch" ? !r.holding
    : filter === "chance" ? r.action === "Kaufen prüfen" : true));
  const converted = rows?.some((r) => r.native_currency && r.native_currency !== r.currency);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Meine Werte</h1>
          <p className="muted">Alles, was du beobachtest oder besitzt. Diese Werte kommen jeden Morgen in deine Zusammenfassung.</p>
        </div>
        <button className="btn primary" onClick={() => setAdding((a) => !a)}>{adding ? "Schließen" : "+ Wert hinzufügen"}</button>
      </div>

      {(adding || (rows && !rows.length)) && (
        <section className="panel">
          <SymbolSearch onPick={add} busySymbol={busy} exclude={(rows || []).map((r) => r.symbol)} actionLabel="Beobachten" />
          <p className="muted small">
            <strong>Tipp:</strong> Den Eintrag mit „gettex · Standard“ wählen – Kurse in Euro, nahezu in Echtzeit und von 8 bis 22 Uhr.
          </p>
        </section>
      )}
      {msg && <p className="ok" role="status">{msg}</p>}
      <ErrorText error={error} />

      {!rows && !error && <Loading />}
      {rows && !rows.length && <Empty title="Noch leer"><p className="muted">Such oben nach deinem ersten Wert.</p></Empty>}

      {rows && rows.length > 0 && (
        <>
          <div className="filter-row">
            <div className="seg" role="tablist">
              {FILTERS.map((f) => (
                <button key={f.id} className={filter === f.id ? "on" : ""} onClick={() => setFilter(f.id)} role="tab" aria-selected={filter === f.id}>{f.label}</button>
              ))}
            </div>
            {converted && <span className="muted small">Kurse teils umgerechnet in {rows.find((r) => r.currency)?.currency} · <Link to="/settings">ändern</Link></span>}
          </div>
          <ul className="stock-list">
            {shown.map((row) => {
              const q = quotes[row.symbol];
              const r = q && q.currency === row.currency ? { ...row, price: q.price, change_pct: q.change_pct ?? row.change_pct } : row;
              const to = `/chart/${encodeURIComponent(r.symbol)}`;
              return (
                <li key={r.symbol} className={`stock-row ${r.holding ? "held" : ""}`}>
                  <Link to={to} className="stock-main">
                    <span className="stock-name">{displayName(r)}</span>
                    <span className="muted small">{displayTicker(r)}{r.exchange ? ` · ${r.exchange}` : ""}{r.note ? ` · „${r.note}“` : ""}</span>
                    {r.holding && (
                      <span className={`held-badge ${tone(r.holding.pl)}`}>
                        💼 {num(r.holding.shares, r.holding.shares % 1 ? 3 : 0)} Stück
                        {r.holding.pl != null && <> · {signedMoney(r.holding.pl, r.holding.currency)} ({pct(r.holding.pl_pct, 1)})</>}
                      </span>
                    )}
                  </Link>
                  {r.error ? (
                    <p className="error small stock-err">{r.error}</p>
                  ) : (
                    <>
                      <Link to={to} className="stock-spark hide-sm" tabIndex={-1} aria-hidden="true"><Sparkline values={r.spark} width={110} height={34} /></Link>
                      <div className="stock-price">
                        <strong>{money(r.price, r.currency)}</strong>
                        <span className={`small ${tone(r.change_pct)}`}>{pct(r.change_pct)}</span>
                        {mode === "pro" && r.rsi != null && <span className="muted small">RSI {num(r.rsi, 0)}</span>}
                      </div>
                      <div className="stock-verdict">
                        <ActionBadge action={r.action} held={!!r.holding} />
                        <span className={`small ${r.holding?.advice ? `advice-inline ${r.holding.advice.level}` : "muted"}`}>
                          {r.holding?.advice ? r.holding.advice.text : r.action !== "Kaufen prüfen" ? r.entry : "Signale sprechen für einen Einstieg"}
                        </span>
                      </div>
                    </>
                  )}
                  <div className="stock-actions">
                    <button className="btn small" onClick={() => setBuying(r.symbol)}>{r.holding ? "Nachkauf" : "Kauf erfassen"}</button>
                    <Link className="link small" to={`/alerts?symbol=${encodeURIComponent(r.symbol)}`}>Alarm</Link>
                    {!r.holding && <button className="link danger small" onClick={() => remove(r)}>Entfernen</button>}
                  </div>
                </li>
              );
            })}
            {!shown.length && <li className="muted">Keine Werte in dieser Auswahl.</li>}
          </ul>
        </>
      )}
      {buying && <BuyDialog symbol={buying} onClose={() => setBuying(null)} onSaved={load} />}
    </>
  );
}
