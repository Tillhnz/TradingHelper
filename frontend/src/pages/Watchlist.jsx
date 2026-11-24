import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import SymbolSearch from "../components/SymbolSearch.jsx";
import AssetRow, { actionHint, priceNums } from "../components/AssetRow.jsx";
import Icon from "../components/Icon.jsx";
import { Empty, ErrorText, Loading, RefreshState } from "../components/ui.jsx";
import { num } from "../fmt.js";
import { useLiveQuotes } from "../live.js";
import { useCachedGet } from "../cache.js";
import { useMode } from "../mode.js";
import { displayName, displayTicker } from "../texts.js";
import { SORTS, useAssetSort } from "../assetSort.js";
import Freshness, { latestTime } from "../components/Freshness.jsx";

const FILTERS = [
  { id: "all", label: "Alle" },
  { id: "held", label: "Im Depot" },
  { id: "watch", label: "Beobachtet" },
  { id: "chance", label: "Gelegenheiten" },
];

export const hasPending = (rows) => Array.isArray(rows) && rows.some((r) => r.pending || r.refreshing);

export default function Watchlist() {
  const { mode } = useMode();
  const overview = useCachedGet("/watchlist/overview", { pollWhile: hasPending });
  const rows = overview.data;
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState("");
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState("all");
  const [arranging, setArranging] = useState(false);
  const sorter = useAssetSort();

  const load = overview.reload;

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
  const sorted = sorter.apply(rows || [], quotes);
  const shown = sorted.filter((r) => (filter === "held" ? r.holding : filter === "watch" ? !r.holding
    : filter === "chance" ? r.action === "Kaufen prüfen" : true));
  const converted = rows?.some((r) => r.native_currency && r.native_currency !== r.currency);
  const stand = latestTime(rows, quotes);

  async function pickSort(id) {
    setError("");
    try { await sorter.setSort(id); } catch (e) { setError(e.message); }
    if (id !== "custom") setArranging(false);
  }

  // Eigene Reihenfolge: aktuelle Anzeige als Ausgangspunkt, dann einen Wert nach oben/unten schieben
  async function shift(symbol, d) {
    const list = sorted.map((r) => r.symbol);
    const i = list.indexOf(symbol);
    const j = i + d;
    if (i < 0 || j < 0 || j >= list.length) return;
    [list[i], list[j]] = [list[j], list[i]];
    setError("");
    try { await sorter.setOrder(list); } catch (e) { setError(e.message); }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Meine Werte</h1>
          <p className="muted">Alles, was du beobachtest oder besitzt. Diese Werte kommen in deine Berichte.</p>
          <RefreshState q={overview} />
          {rows?.length > 0 && <p className="muted small" style={{ margin: "0.2rem 0 0" }}><Freshness asOf={stand.asOf} delay={stand.delay} dayOnly={stand.dayOnly} at={stand.asOf ? null : overview.at} /></p>}
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
      <ErrorText error={error || overview.error} />

      {!rows && !error && !overview.error && <Loading />}
      {rows && !rows.length && <Empty title="Noch leer"><p className="muted">Such oben nach deinem ersten Wert.</p></Empty>}

      {rows && rows.length > 0 && (
        <>
          <div className="filter-row">
            <div className="seg" role="tablist">
              {FILTERS.map((f) => (
                <button key={f.id} className={filter === f.id ? "on" : ""} onClick={() => setFilter(f.id)} role="tab" aria-selected={filter === f.id}>{f.label}</button>
              ))}
            </div>
            <div className="sort-ctl">
              <span className="muted small">Sortieren</span>
              <div className="seg" role="group" aria-label="Sortierung">
                {SORTS.map((o) => (
                  <button key={o.id} className={sorter.sort === o.id ? "on" : ""} title={o.title} onClick={() => pickSort(o.id)}>{o.label}</button>
                ))}
              </div>
              {sorter.sort === "custom" && (
                <button className={`btn small ${arranging ? "primary" : ""}`} onClick={() => { setFilter("all"); setArranging((a) => !a); }}>
                  {arranging ? "Fertig" : "Reihenfolge ändern"}
                </button>
              )}
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
              if (arranging) {
                const idx = sorted.findIndex((x) => x.symbol === r.symbol);
                return (
                  <li key={r.symbol} className="arrange-row">
                    <span className="arrange-name"><strong>{displayName(r)}</strong><span className="muted small">{displayTicker(r)}</span></span>
                    <span className="arrange-btns">
                      <button className="icon-btn" onClick={() => shift(r.symbol, -1)} disabled={idx === 0} aria-label={`${displayName(r)} nach oben`}><Icon name="chevup" /></button>
                      <button className="icon-btn" onClick={() => shift(r.symbol, 1)} disabled={idx === sorted.length - 1} aria-label={`${displayName(r)} nach unten`}><Icon name="chevdown" /></button>
                    </span>
                  </li>
                );
              }
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
