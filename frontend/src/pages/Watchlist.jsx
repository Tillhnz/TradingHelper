import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import SymbolSearch from "../components/SymbolSearch.jsx";
import AssetRow, { actionHint, priceNums } from "../components/AssetRow.jsx";
import Icon from "../components/Icon.jsx";
import { Empty, ErrorText, Loading } from "../components/ui.jsx";
import { num } from "../fmt.js";
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

  const quotes = useLiveQuotes((rows || []).map((r) => r.symbol));
  const shown = (rows || []).filter((r) => (filter === "held" ? r.holding : filter === "watch" ? !r.holding
    : filter === "chance" ? r.action === "Kaufen prüfen" : true));
  const converted = rows?.some((r) => r.native_currency && r.native_currency !== r.currency);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Meine Werte</h1>
          <p className="muted">Alles, was du beobachtest oder besitzt. Diese Werte kommen in deine Berichte.</p>
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
          <ul className="asset-list">
            {shown.map((row, i) => {
              const q = quotes[row.symbol];
              const r = q && q.currency === row.currency ? { ...row, price: q.price, change_pct: q.change_pct ?? row.change_pct } : row;
              const h = r.holding;
              // Hier steht immer der Kurs – dein Vermögen im Wert siehst du auf seiner Seite (oder im Depot)
              const nums = priceNums(r.price, r.change_pct, r.currency);
              const meta = h?.shares
                ? <><span className="held-mark" title="Im Depot"><Icon name="briefcase" /></span>{displayTicker(r)}</>
                : <>{displayTicker(r)}{mode === "pro" && r.rsi != null ? ` · RSI ${num(r.rsi, 0)}` : ""}</>;
              const hint = h?.shares ? actionHint(h.advice)
                : r.action === "Kaufen prüfen" ? { level: "good", text: "Signale sprechen für einen Einstieg" }
                : filter === "chance" || mode === "pro" ? (r.entry ? { level: "info", text: r.entry } : null) : null;
              return (
                <AssetRow key={r.symbol} symbol={r.symbol} name={displayName(r)} meta={meta} action={r.action} held={!!h?.shares}
                  top={nums.top} bottom={nums.bottom} hint={hint} error={r.error} bo={r.breakout} index={i} />
              );
            })}
            {!shown.length && <li className="muted asset-empty">Keine Werte in dieser Auswahl.</li>}
          </ul>
          <p className="muted small list-foot">Antippen öffnet den Wert mit Chart, Einschätzung, Kauf und Alarm.</p>
        </>
      )}
    </>
  );
}
