import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";
import { CURRENCY_LABEL, money } from "../fmt.js";
import Modal from "./Modal.jsx";
import SymbolSearch from "./SymbolSearch.jsx";

const today = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
const n = (v) => (v === "" || v === null || v === undefined ? null : Number(String(v).replace(",", ".")));

/** Grafik Stopp → Kauf → Ziel: rote Verlust- und grüne Gewinnzone, Markierung beim aktuellen Kurs. */
export function RiskBar({ entry, stop, target, current, currency }) {
  if (!entry) return null;
  const lo = Math.min(...[stop, entry, current].filter(Boolean)) * 0.995;
  const hi = Math.max(...[target, entry, current, entry * 1.02].filter(Boolean)) * 1.005;
  const x = (v) => `${((v - lo) / (hi - lo)) * 100}%`;
  return (
    <div className="riskbar" aria-hidden="true">
      <div className="riskbar-track">
        {stop && <div className="riskbar-loss" style={{ left: x(stop), width: `calc(${x(entry)} - ${x(stop)})` }} />}
        <div className="riskbar-gain" style={{ left: x(entry), width: target ? `calc(${x(target)} - ${x(entry)})` : `calc(100% - ${x(entry)})` }} />
        <div className="riskbar-entry" style={{ left: x(entry) }} />
        {current && <div className="riskbar-now" style={{ left: x(current) }} title="aktueller Kurs" />}
      </div>
      <div className="riskbar-labels small">
        {stop && <span style={{ left: x(stop) }} className="neg">Stopp {money(stop, currency)}</span>}
        <span style={{ left: x(entry) }}>Kauf {money(entry, currency)}</span>
        {target && <span style={{ left: x(target) }} className="pos">Ziel {money(target, currency)}</span>}
      </div>
    </div>
  );
}

/**
 * Kauf erfassen. Vorbelegt aus Chart und Einstiegsplan (Kurs, Stopp, Ziel, Stückzahl).
 * Kurse gelten in der gewählten Währung; leer = Handelswährung des Börsenplatzes.
 */
export default function BuyDialog({ symbol: fixedSymbol, info = {}, defaults = {}, onClose, onSaved }) {
  const [symbol, setSymbol] = useState(fixedSymbol || "");
  const [meta, setMeta] = useState(info);
  const shownCcy = meta.currency && meta.currency !== meta.native_currency ? meta.currency : "";
  const [form, setForm] = useState({
    quantity: defaults.quantity ?? "", buy_price: defaults.price ?? "", buy_date: today(), fees: "",
    currency: shownCcy, stop: defaults.stop ?? "", target: defaults.target ?? "", note: "", create_alerts: true,
  });
  const [depot, setDepot] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/settings").then((r) => setDepot(Number(r.fields.portfolio_size?.value || 0))).catch(() => {});
  }, []);

  async function pick(r) {
    setSymbol(r.symbol);
    setError("");
    try {
      const a = await api.get(`/analysis/${encodeURIComponent(r.symbol)}?interval=1d&with_news=false`);
      setMeta({ currency: a.currency, native_currency: a.native_currency, name: a.name, exchange: a.exchange, price: a.last_close });
      const best = a.entry?.setups?.find((s) => s.ok) || {};
      const conv = a.currency && a.currency !== a.native_currency ? a.currency : "";
      setForm((f) => ({
        ...f, currency: conv, buy_price: a.last_close,
        stop: best.stop ?? a.recommendation?.stop ?? "", target: best.target ?? a.recommendation?.target ?? "",
        quantity: best.position?.shares ?? f.quantity,
      }));
    } catch (e) {
      setError(e.message);
    }
  }

  const ccy = form.currency || meta.native_currency;
  const qty = n(form.quantity), price = n(form.buy_price), stop = n(form.stop), target = n(form.target), fees = n(form.fees) || 0;
  const calc = useMemo(() => {
    if (!qty || !price) return null;
    const invest = qty * price + fees;
    const risk = stop ? (price - stop) * qty + fees : null;
    const chance = target ? (target - price) * qty - fees : null;
    return {
      invest, risk, chance,
      crv: risk && chance && risk > 0 ? chance / risk : null,
      riskPct: risk && depot ? (risk / depot) * 100 : null,
      investPct: depot ? (invest / depot) * 100 : null,
    };
  }, [qty, price, stop, target, fees, depot]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = {
        symbol, quantity: qty, buy_price: price, buy_date: form.buy_date, fees, currency: form.currency || "",
        stop: stop || null, target: target || null, note: form.note, create_alerts: form.create_alerts && !!(stop || target),
      };
      const r = await api.post("/positions", body);
      onSaved?.(r);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const ccyOptions = ["", "EUR", "USD", "CHF", "GBP"].filter((c) => c === "" || c !== meta.native_currency);

  return (
    <Modal title={symbol ? `Kauf erfassen · ${symbol}` : "Kauf erfassen"} onClose={onClose} wide>
      {!symbol ? (
        <SymbolSearch onPick={pick} actionLabel="Auswählen" />
      ) : (
        <form onSubmit={save}>
          {(meta.name || meta.exchange) && <p className="muted small">{[meta.name, meta.exchange].filter(Boolean).join(" · ")}</p>}
          <div className="form-grid">
            <label>Stückzahl<input inputMode="decimal" value={form.quantity} onChange={set("quantity")} required autoFocus /></label>
            <label>Kaufkurs <span className="hint">je Stück, in {ccy || "Punkten"}</span><input inputMode="decimal" value={form.buy_price} onChange={set("buy_price")} required /></label>
            <label>Kaufdatum<input type="date" value={form.buy_date} max={today()} onChange={set("buy_date")} required /></label>
            <label>Gebühren <span className="hint">optional</span><input inputMode="decimal" value={form.fees} onChange={set("fees")} placeholder="0" /></label>
            {meta.native_currency && (
              <label>
                Währung der Kurse
                <select value={form.currency} onChange={set("currency")}>
                  {ccyOptions.map((c) => <option key={c} value={c}>{c === "" ? `${CURRENCY_LABEL.native} (${meta.native_currency})` : CURRENCY_LABEL[c]}</option>)}
                </select>
              </label>
            )}
            <label>Stopp <span className="hint">Verlustgrenze</span><input inputMode="decimal" value={form.stop} onChange={set("stop")} /></label>
            <label>Ziel <span className="hint">optional</span><input inputMode="decimal" value={form.target} onChange={set("target")} /></label>
            <label className="span-all">Notiz <span className="hint">optional, z. B. Grund für den Kauf</span><input value={form.note} onChange={set("note")} maxLength={300} /></label>
          </div>

          {calc && (
            <div className="buy-preview">
              <RiskBar entry={price} stop={stop} target={target} current={meta.price} currency={ccy} />
              <div className="stats stats-wide">
                <div className="stat"><span className="stat-label">Einsatz</span><strong className="stat-value">{money(calc.invest, ccy)}</strong>
                  {calc.investPct !== null && <span className="muted small">{calc.investPct.toFixed(1).replace(".", ",")} % vom Depot</span>}</div>
                <div className="stat neg"><span className="stat-label">Risiko bis Stopp</span><strong className="stat-value">{calc.risk !== null ? `−${money(calc.risk, ccy)}` : "–"}</strong>
                  {calc.riskPct !== null && <span className="muted small">{calc.riskPct.toFixed(2).replace(".", ",")} % vom Depot</span>}</div>
                <div className="stat pos"><span className="stat-label">Chance bis Ziel</span><strong className="stat-value">{calc.chance !== null ? `+${money(calc.chance, ccy)}` : "–"}</strong></div>
                <div className="stat"><span className="stat-label">Chance/Risiko</span><strong className="stat-value">{calc.crv ? calc.crv.toFixed(1).replace(".", ",") : "–"}</strong></div>
              </div>
              {stop && price && stop >= price && <p className="error small">Der Stopp liegt über dem Kaufkurs.</p>}
            </div>
          )}

          <label className="check">
            <input type="checkbox" checked={form.create_alerts} onChange={set("create_alerts")} disabled={!stop && !target} />
            Alarme für Stopp und Ziel anlegen (Push, wenn erreicht)
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <div className="actions">
            <button className="btn primary" disabled={busy}>{busy ? "Speichere …" : "Kauf speichern"}</button>
            <button type="button" className="btn" onClick={onClose}>Abbrechen</button>
            {!fixedSymbol && <button type="button" className="link small" onClick={() => setSymbol("")}>Anderen Wert wählen</button>}
          </div>
        </form>
      )}
      {!symbol && error && <p className="error">{error}</p>}
    </Modal>
  );
}
