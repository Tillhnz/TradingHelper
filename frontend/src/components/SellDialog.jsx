import { useState } from "react";
import { api } from "../api.js";
import { money, num, pct, signedMoney, tone } from "../fmt.js";
import Modal from "./Modal.jsx";

const today = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
};
const nowTime = () => new Date().toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
const n = (v) => (v === "" || v == null ? null : Number(String(v).replace(",", ".")));
const date = (iso) => String(iso).split("-").reverse().join(".");
const qty = (q) => num(q, q % 1 ? 3 : 0);

/** Kurs eines Blocks „jetzt“: Live-Kurs der Seite, wenn er in derselben Währung vorliegt, sonst der zuletzt bewertete. */
export function nowPrice(block, live, liveCcy) {
  const v = live != null && (!liveCcy || liveCcy === block.display_currency) ? live : block.price;
  return v != null ? Math.round(v * 100) / 100 : "";
}

/**
 * Schnellverkauf wie der Schnellkauf: Kurs und Uhrzeit von jetzt sind übernommen, ein Tipp auf „Verkaufen“ genügt.
 * Verkauft wird immer ein ganzer Block (ein Kauf). Bei mehreren Blöcken wählst du, welcher es ist.
 */
export default function SellDialog({ blocks, initialId, live, liveCcy, name, onClose, onSaved }) {
  const [id, setId] = useState(initialId ?? blocks[0]?.id);
  const block = blocks.find((b) => b.id === id) || blocks[0];
  const [f, setF] = useState({ sell_price: nowPrice(block, live, liveCcy), sell_date: today(), sell_time: nowTime(), sell_fees: "" });
  const [details, setDetails] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const c = block.display_currency;

  function choose(b) {
    setId(b.id);
    setF((x) => ({ ...x, sell_price: nowPrice(b, live, liveCcy) }));
  }

  async function save(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api.patch(`/positions/${block.id}`, {
        sell_price: n(f.sell_price), sell_date: f.sell_date, sell_time: f.sell_time || "", sell_fees: n(f.sell_fees) || 0,
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  const sp = n(f.sell_price);
  const pl = sp ? (sp - block.buy_price) * block.quantity - (block.fees || 0) - (n(f.sell_fees) || 0) : null;
  const plPct = sp ? (sp / block.buy_price - 1) * 100 : null;

  return (
    <Modal title={`Verkauf · ${name || block.symbol.replace(/\.GTX$/, "")}`} onClose={onClose}>
      <form onSubmit={save}>
        {blocks.length > 1 && (
          <fieldset className="block-pick">
            <legend className="small muted">Welcher Block?</legend>
            {blocks.map((b) => (
              <label key={b.id} className={`block-opt ${b.id === block.id ? "on" : ""}`}>
                <input type="radio" name="block" checked={b.id === block.id} onChange={() => choose(b)} />
                <span className="block-opt-main">
                  <strong>{qty(b.quantity)} Stück</strong>
                  <span className="small muted">{date(b.buy_date)}{b.buy_time ? ` ${b.buy_time}` : ""} · à {money(b.buy_price, b.display_currency)}</span>
                </span>
                <span className={`small ${tone(b.pl)}`}>{signedMoney(b.pl, b.display_currency)}</span>
              </label>
            ))}
          </fieldset>
        )}
        <div className="quick-buy">
          <div className="quick-now">
            <span className="muted small">{qty(block.quantity)} Stück verkauft zu</span>
            <strong>{sp ? money(sp, c) : "–"}</strong>
            <span className="muted small">am {date(f.sell_date)}{f.sell_time ? ` um ${f.sell_time} Uhr` : ""}</span>
          </div>
          {pl !== null && (
            <div className={`quick-now ${tone(pl)}`}>
              <span className="muted small">Ergebnis</span>
              <strong>{signedMoney(pl, c)}</strong>
              <span className="small">{pct(plPct)}</span>
            </div>
          )}
        </div>
        {!details && (
          <p className="small muted quick-sum">
            Gekauft am {date(block.buy_date)} zu {money(block.buy_price, c)}
            {" · "}<button type="button" className="link small" onClick={() => setDetails(true)}>Kurs oder Zeit ändern</button>
          </p>
        )}
        <div className={`form-grid ${details ? "" : "collapsed"}`}>
          <label>Verkaufskurs <span className="hint">je Stück, in {c}</span><input inputMode="decimal" value={f.sell_price} onChange={set("sell_price")} required /></label>
          <label>Datum<input type="date" value={f.sell_date} max={today()} min={block.buy_date} onChange={set("sell_date")} required /></label>
          <label>Uhrzeit <span className="hint">optional</span><input type="time" value={f.sell_time} onChange={set("sell_time")} /></label>
          <label>Gebühren <span className="hint">optional</span><input inputMode="decimal" value={f.sell_fees} onChange={set("sell_fees")} placeholder="0" /></label>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="actions">
          <button className="btn primary btn-sell" disabled={busy}>Verkaufen</button>
          <button type="button" className="btn" onClick={onClose}>Abbrechen</button>
        </div>
      </form>
    </Modal>
  );
}
