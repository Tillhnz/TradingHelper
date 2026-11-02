import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { ActionBadge, Empty, ErrorText, Loading, Sparkline } from "../components/ui.jsx";
import { num, pct, price, tone } from "../fmt.js";

const EXAMPLES = ["AAPL", "MSFT", "NVDA", "SAP.DE", "^GDAXI", "BTC-USD", "IWDA.AS"];

export default function Watchlist() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [symbol, setSymbol] = useState("");
  const [note, setNote] = useState("");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    try {
      setRows(await api.get("/watchlist/overview"));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function add(e) {
    e.preventDefault();
    if (!symbol.trim()) return;
    setAdding(true);
    setError("");
    try {
      await api.post("/watchlist", { symbol: symbol.trim(), note });
      setSymbol("");
      setNote("");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setAdding(false);
    }
  }

  async function remove(sym) {
    if (!window.confirm(`${sym} aus der Watchlist entfernen?`)) return;
    try {
      await api.del(`/watchlist/${encodeURIComponent(sym)}`);
      setRows((r) => r.filter((x) => x.symbol !== sym));
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Watchlist</h1>
          <p className="muted">Diese Werte landen im Morgenreport.</p>
        </div>
      </div>

      <form className="inline-form" onSubmit={add}>
        <label className="grow">
          Symbol <span className="hint">Yahoo-Schreibweise</span>
          <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="z. B. SAP.DE" list="symbol-examples" required />
          <datalist id="symbol-examples">{EXAMPLES.map((x) => <option key={x} value={x} />)}</datalist>
        </label>
        <label className="grow">
          Notiz <span className="hint">optional</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} />
        </label>
        <button className="btn primary" disabled={adding}>{adding ? "Prüfe …" : "Hinzufügen"}</button>
      </form>
      <p className="muted small">
        Deutsche Börsen mit Endung (<code>SAP.DE</code> Xetra), Indizes mit ^ (<code>^GDAXI</code>), Krypto mit Währung (<code>BTC-EUR</code>), Devisen wie <code>EURUSD=X</code>.
      </p>
      <ErrorText error={error} />

      {!rows && !error && <Loading />}
      {rows && !rows.length && (
        <Empty title="Noch leer">
          <p className="muted">Trag oben dein erstes Symbol ein.</p>
        </Empty>
      )}
      {rows && rows.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Symbol</th><th className="hide-sm">30 Tage</th><th className="num">Kurs</th><th className="num">Tag</th>
                <th className="num hide-sm">RSI</th><th>Einschätzung</th><th className="hide-sm">Notiz</th><th />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.symbol}>
                  <td><Link to={`/chart/${encodeURIComponent(r.symbol)}`} className="sym">{r.symbol}</Link></td>
                  {r.error ? (
                    <td colSpan={6} className="error small">{r.error}</td>
                  ) : (
                    <>
                      <td className="hide-sm"><Sparkline values={r.spark} /></td>
                      <td className="num">{price(r.price)}</td>
                      <td className={`num ${tone(r.change_pct)}`}>{pct(r.change_pct)}</td>
                      <td className="num hide-sm">{num(r.rsi, 0)}</td>
                      <td><ActionBadge action={r.action} /></td>
                      <td className="muted small hide-sm">{r.note}</td>
                    </>
                  )}
                  <td className="row-actions">
                    <Link className="link small" to={`/alerts?symbol=${encodeURIComponent(r.symbol)}`}>Alarm</Link>
                    <button className="link danger small" onClick={() => remove(r.symbol)}>Entfernen</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
