import { useState } from "react";
import { api } from "../api.js";
import { RiskBar } from "./BuyDialog.jsx";
import Modal from "./Modal.jsx";
import { signedMoney, tone } from "../fmt.js";
import { displayName } from "../texts.js";

const today = () => new Date().toISOString().slice(0, 10);
const n = (v) => (v === "" || v == null ? null : Number(String(v).replace(",", ".")));

/** Position bearbeiten (mode="edit") oder Verkauf erfassen (mode="sell"). */
export default function EditDialog({ pos, mode, onClose, onSaved }) {
  const [f, setF] = useState(mode === "sell"
    ? { sell_price: pos.price ?? "", sell_date: today(), sell_fees: "" }
    : { stop: pos.stop_base ?? pos.stop ?? "", trail_pct: pos.trail_pct ?? "", target: pos.target ?? "", note: pos.note ?? "", quantity: pos.quantity, buy_price: pos.buy_price, buy_date: pos.buy_date, buy_time: pos.buy_time ?? "", fees: pos.fees ?? 0 });
  const [error, setError] = useState("");
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const c = pos.display_currency;

  async function save(e) {
    e.preventDefault();
    setError("");
    const body = mode === "sell"
      ? { sell_price: n(f.sell_price), sell_date: f.sell_date, sell_fees: n(f.sell_fees) || 0 }
      : { stop: n(f.stop) ?? 0, trail_pct: n(f.trail_pct) ?? 0, target: n(f.target) ?? 0, note: f.note, quantity: n(f.quantity), buy_price: n(f.buy_price), buy_date: f.buy_date, buy_time: f.buy_time || "", fees: n(f.fees) || 0 };
    try {
      await api.patch(`/positions/${pos.id}`, body);
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
    }
  }

  const sellPl = mode === "sell" && n(f.sell_price) ? (n(f.sell_price) - pos.buy_price) * pos.quantity - (pos.fees || 0) - (n(f.sell_fees) || 0) : null;

  return (
    <Modal title={`${mode === "sell" ? "Verkauf erfassen" : "Position bearbeiten"} · ${displayName(pos)}`} onClose={onClose}>
      <form onSubmit={save}>
        <div className="form-grid">
          {mode === "sell" ? (
            <>
              <label>Verkaufskurs <span className="hint">in {c}</span><input inputMode="decimal" value={f.sell_price} onChange={set("sell_price")} required autoFocus /></label>
              <label>Verkaufsdatum<input type="date" value={f.sell_date} max={today()} onChange={set("sell_date")} required /></label>
              <label>Gebühren<input inputMode="decimal" value={f.sell_fees} onChange={set("sell_fees")} placeholder="0" /></label>
            </>
          ) : (
            <>
              <label>Stopp <span className="hint">leer = entfernen</span><input inputMode="decimal" value={f.stop} onChange={set("stop")} autoFocus /></label>
              <label>Ziel<input inputMode="decimal" value={f.target} onChange={set("target")} /></label>
              <label>Stopp mitlaufen lassen <span className="hint">Abstand in %, leer = aus{pos.trail_suggest_pct ? `; Empfehlung ${String(pos.trail_suggest_pct).replace(".", ",")} %` : ""}</span>
                <input inputMode="decimal" value={f.trail_pct} onChange={set("trail_pct")} /></label>
              <label>Stückzahl<input inputMode="decimal" value={f.quantity} onChange={set("quantity")} required /></label>
              <label>Kaufkurs <span className="hint">in {c}</span><input inputMode="decimal" value={f.buy_price} onChange={set("buy_price")} required /></label>
              <label>Kaufdatum<input type="date" value={f.buy_date} max={today()} onChange={set("buy_date")} required /></label>
              <label>Uhrzeit <span className="hint">optional, für den Tagesverlauf</span><input type="time" value={f.buy_time} onChange={set("buy_time")} /></label>
              <label>Gebühren<input inputMode="decimal" value={f.fees} onChange={set("fees")} /></label>
              <label className="span-all">Notiz<input value={f.note} onChange={set("note")} maxLength={300} /></label>
            </>
          )}
        </div>
        {mode !== "sell" && <RiskBar entry={n(f.buy_price)} stop={n(f.stop)} target={n(f.target)} current={pos.price} currency={c} />}
        {sellPl !== null && <p className={`big-pl ${tone(sellPl)}`}>Ergebnis {signedMoney(sellPl, c)}</p>}
        {error && <p className="error" role="alert">{error}</p>}
        <div className="actions">
          <button className="btn primary">Speichern</button>
          <button type="button" className="btn" onClick={onClose}>Abbrechen</button>
          {mode !== "sell" && (
            <button type="button" className="btn danger push-right" onClick={async () => {
              if (!window.confirm("Diesen Kauf wirklich löschen? Das lässt sich nicht rückgängig machen.")) return;
              try { await api.del(`/positions/${pos.id}`); onSaved(); onClose(); } catch (err) { setError(err.message); }
            }}>Kauf löschen</button>
          )}
        </div>
      </form>
    </Modal>
  );
}

