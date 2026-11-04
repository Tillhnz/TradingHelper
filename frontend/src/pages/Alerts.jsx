import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { Empty, ErrorText, Loading } from "../components/ui.jsx";
import { CURRENCY_LABEL, dateTime } from "../fmt.js";
import { displayName, displayTicker } from "../texts.js";
import { Link } from "react-router-dom";

const PARAM_LABEL = {
  value: "Wert", period: "Periode", fast: "Schneller MA", slow: "Langsamer MA", type: "Art",
  k: "Std.-Abw.", factor: "Faktor", lookback: "Perioden",
};
const INTERVAL_LABEL = { "5m": "5 Minuten", "15m": "15 Minuten", "30m": "30 Minuten", "1h": "1 Stunde", "1d": "Tag", "1wk": "Woche" };

function describeParams(params) {
  return Object.entries(params).map(([k, v]) => `${PARAM_LABEL[k] || k} ${v}`).join(", ");
}

export default function Alerts() {
  const [search] = useSearchParams();
  const [meta, setMeta] = useState(null);
  const [list, setList] = useState(null);
  const [log, setLog] = useState([]);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [form, setForm] = useState({ symbol: search.get("symbol") || "", kind: "rsi_below", interval: "1d", once: false, params: {}, currency: null });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [k, a, l] = await Promise.all([api.get("/alerts/kinds"), api.get("/alerts"), api.get("/alerts/log?limit=30")]);
      setMeta(k);
      setForm((f) => (f.currency === null ? { ...f, currency: k.display_currency === "native" ? "" : k.display_currency } : f));
      setList(a);
      setLog(l);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const kind = useMemo(() => meta?.kinds.find((k) => k.name === form.kind), [meta, form.kind]);
  // Nur Kurs-Bedingungen haben Werte in einer Währung (RSI, MACD usw. sind währungsunabhängig genug)
  const priceKind = ["price_above", "price_below", "cross_up", "cross_down"].includes(form.kind);
  const kindDesc = useMemo(() => Object.fromEntries((meta?.kinds || []).map((k) => [k.name, k.description])), [meta]);

  function setParam(key, value) {
    setForm((f) => ({ ...f, params: { ...f.params, [key]: value } }));
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setMsg("");
    const params = Object.fromEntries(Object.entries(form.params).filter(([k, v]) => v !== "" && v !== undefined && kind.params[k] !== undefined));
    try {
      await api.post("/alerts", { symbol: form.symbol, kind: form.kind, interval: form.interval, once: form.once, params, currency: priceKind ? form.currency || "" : "" });
      setForm((f) => ({ ...f, params: {} }));
      setMsg("Alarm angelegt.");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function toggle(a) {
    try {
      const upd = await api.patch(`/alerts/${a.id}`, { active: !a.active });
      setList((l) => l.map((x) => (x.id === a.id ? upd : x)));
    } catch (e) {
      setError(e.message);
    }
  }

  async function remove(a) {
    if (!window.confirm(`Alarm für ${a.symbol} löschen?`)) return;
    try {
      await api.del(`/alerts/${a.id}`);
      setList((l) => l.filter((x) => x.id !== a.id));
    } catch (e) {
      setError(e.message);
    }
  }

  async function checkNow() {
    setMsg("");
    setError("");
    try {
      const r = await api.post("/alerts/check");
      setMsg(r.fired.length ? `${r.fired.length} Alarm(e) ausgelöst und per Push gesendet.` : "Keine Bedingung erfüllt.");
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  if (!meta && !error) return <Loading />;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Alarme</h1>
          <p className="muted">Wie bei TradingView: Bedingung festlegen, Push kommt aufs Handy.</p>
        </div>
        <button className="btn" onClick={checkNow}>Jetzt prüfen</button>
      </div>
      <ErrorText error={error} />
      {msg && <p className="note" role="status">{msg}</p>}

      {meta && (
        <form className="panel" onSubmit={submit}>
          <h2>Neuer Alarm</h2>
          <div className="form-grid">
            <label>
              Symbol
              <input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })} placeholder="z. B. AAPL" required />
            </label>
            <label>
              Bedingung
              <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value, params: {} })}>
                {meta.kinds.map((k) => <option key={k.name} value={k.name}>{k.description}</option>)}
              </select>
            </label>
            {kind && Object.entries(kind.params).map(([key, def]) => (
              <label key={key}>
                {PARAM_LABEL[key] || key} {def === null ? <span className="hint">Pflicht</span> : <span className="hint">Standard {String(def)}</span>}
                {key === "type" ? (
                  <select value={form.params.type ?? def} onChange={(e) => setParam("type", e.target.value)}>
                    <option value="sma">SMA (einfach)</option>
                    <option value="ema">EMA (exponentiell)</option>
                  </select>
                ) : (
                  <input type="number" step="any" value={form.params[key] ?? ""} placeholder={def === null ? "" : String(def)}
                    onChange={(e) => setParam(key, e.target.value)} required={def === null} />
                )}
              </label>
            ))}
            {priceKind && (
              <label>
                Währung des Werts
                <select value={form.currency ?? ""} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
                  <option value="">{CURRENCY_LABEL.native} des Symbols</option>
                  {meta.currencies.map((c) => <option key={c} value={c}>{CURRENCY_LABEL[c] || c}</option>)}
                </select>
              </label>
            )}
            <label>
              Kerzen
              <select value={form.interval} onChange={(e) => setForm({ ...form, interval: e.target.value })}>
                {meta.intervals.filter((iv) => !form.symbol.endsWith(".GTX") || ["1d", "1wk"].includes(iv)).map((iv) => <option key={iv} value={iv}>{INTERVAL_LABEL[iv] || iv}</option>)}
              </select>
            </label>
            <label className="check">
              <input type="checkbox" checked={form.once} onChange={(e) => setForm({ ...form, once: e.target.checked })} />
              Nur einmal auslösen, danach pausieren
            </label>
          </div>
          <div className="actions">
            <button className="btn primary" disabled={busy}>{busy ? "Speichere …" : "Alarm anlegen"}</button>
            <span className="muted small">Kreuzungs-Alarme vergleichen die letzten beiden Kerzen (wie ta.crossover).</span>
          </div>
        </form>
      )}

      <h2 className="section-title">Deine Alarme</h2>
      {list && !list.length && <Empty title="Noch keine Alarme"><p className="muted">Lege oben deinen ersten an.</p></Empty>}
      {list && list.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Symbol</th><th>Bedingung</th><th className="hide-sm">Kerzen</th><th className="hide-sm">Zuletzt</th><th>Aktiv</th><th /></tr>
            </thead>
            <tbody>
              {list.map((a) => (
                <tr key={a.id} className={a.active ? "" : "inactive"}>
                  <td><Link className="sym" to={`/chart/${encodeURIComponent(a.symbol)}`}>{displayName(a)}</Link><div className="muted small">{displayTicker(a)}</div></td>
                  <td>
                    {kindDesc[a.kind] || a.kind}
                    {Object.keys(a.params).length > 0 && <span className="muted small"> · {describeParams(a.params)}{["price_above", "price_below", "cross_up", "cross_down"].includes(a.kind) && (a.currency || a.native_currency) ? ` ${a.currency || a.native_currency}` : ""}</span>}
                    {a.once && <span className="muted small"> · einmalig</span>}
                  </td>
                  <td className="hide-sm">{INTERVAL_LABEL[a.interval] || a.interval}</td>
                  <td className="muted small hide-sm">{dateTime(a.last_triggered)}</td>
                  <td>
                    <label className="switch">
                      <input type="checkbox" checked={a.active} onChange={() => toggle(a)} aria-label={`Alarm ${a.symbol} aktiv`} />
                      <span />
                    </label>
                  </td>
                  <td className="row-actions"><button className="link danger small" onClick={() => remove(a)}>Löschen</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 className="section-title">Verlauf</h2>
      {log.length ? (
        <ul className="log-list">
          {log.map((l) => <li key={l.id}><span className="muted small">{dateTime(l.triggered_at)}</span> <Link to={`/chart/${encodeURIComponent(l.symbol)}`}><strong>{displayName(l)}</strong></Link> {l.message}</li>)}
        </ul>
      ) : <p className="muted">Noch nichts ausgelöst.</p>}
    </>
  );
}
