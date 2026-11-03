import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import SymbolSearch from "../components/SymbolSearch.jsx";
import { ActionBadge, Empty, ErrorText, Loading, Sparkline } from "../components/ui.jsx";
import { money, num, pct, tone } from "../fmt.js";

export default function Watchlist() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState("");

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
      setMsg(`${info.added}${info.exchange ? ` (${info.exchange}${info.currency ? `, ${info.currency}` : ""})` : ""} hinzugefügt.`);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
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

  const ccy = rows?.find((r) => r.currency)?.currency;
  const mixed = rows?.some((r) => r.native_currency && r.native_currency !== r.currency);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Watchlist</h1>
          <p className="muted">Diese Werte landen im Morgenreport.</p>
        </div>
      </div>

      <section className="panel">
        <SymbolSearch onPick={add} busySymbol={busy} exclude={(rows || []).map((r) => r.symbol)} />
        <p className="muted small">
          Derselbe Wert ist oft an mehreren Börsen gelistet. Für Kurse in Euro einen deutschen Platz wählen (Xetra, Frankfurt, Stuttgart …),
          oder unter Einstellungen die Anzeigewährung festlegen.
        </p>
      </section>
      {msg && <p className="ok" role="status">{msg}</p>}
      <ErrorText error={error} />

      {!rows && !error && <Loading />}
      {rows && !rows.length && (
        <Empty title="Noch leer">
          <p className="muted">Such oben nach deinem ersten Wert.</p>
        </Empty>
      )}
      {rows && rows.length > 0 && (
        <>
          {mixed && ccy && (
            <p className="muted small">Kurse umgerechnet in {ccy} (Tageskurs). Ändern unter <Link to="/settings">Einstellungen → Anzeigewährung</Link>.</p>
          )}
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Wert</th><th className="hide-sm">30 Tage</th><th className="num">Kurs</th><th className="num">Tag</th>
                  <th className="num hide-sm">RSI</th><th>Einschätzung</th><th />
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.symbol}>
                    <td>
                      <Link to={`/chart/${encodeURIComponent(r.symbol)}`} className="sym">{r.symbol}</Link>
                      <div className="muted small cell-sub">
                        {r.name && <span>{r.name}</span>}
                        {r.exchange && <span>{r.exchange}{r.native_currency ? ` · ${r.native_currency}` : ""}</span>}
                        {r.note && <span>„{r.note}“</span>}
                      </div>
                    </td>
                    {r.error ? (
                      <td colSpan={5} className="error small">{r.error}</td>
                    ) : (
                      <>
                        <td className="hide-sm"><Sparkline values={r.spark} /></td>
                        <td className="num">{money(r.price, r.currency)}</td>
                        <td className={`num ${tone(r.change_pct)}`}>{pct(r.change_pct)}</td>
                        <td className="num hide-sm">{num(r.rsi, 0)}</td>
                        <td><ActionBadge action={r.action} /></td>
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
        </>
      )}
    </>
  );
}
