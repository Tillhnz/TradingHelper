import { useState } from "react";
import { api } from "../api.js";
import { money, num, pct, signedMoney, tone } from "../fmt.js";
import { RiskBar } from "./BuyDialog.jsx";
import EditDialog from "./EditDialog.jsx";

const date = (iso) => (iso ? new Date(iso).toLocaleDateString("de-DE") : "–");
const qty = (q) => num(q, q % 1 ? 3 : 0);

/** „Mein Bestand“ auf der Seite eines Werts: Zusammenfassung, Rat für Halter und alle Käufe mit Aktionen. */
export default function HoldingPanel({ holding, onChanged, onBuyMore }) {
  const [dialog, setDialog] = useState(null);
  const [error, setError] = useState("");
  if (!holding?.items?.length) return null;
  const s = holding.summary;
  const c = s.currency;
  const open = holding.items.filter((p) => !p.closed);
  const closed = holding.items.filter((p) => p.closed);

  async function act(fn) {
    setError("");
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <section className={`panel holding ${s.pl > 0 ? "gain" : s.pl < 0 ? "loss" : ""}`}>
      <div className="panel-head">
        <h2>Mein Bestand</h2>
        <button className="btn small primary" onClick={onBuyMore}>{s.shares ? "Nachkauf erfassen" : "Kauf erfassen"}</button>
      </div>

      {s.shares > 0 ? (
        <>
          <div className="holding-top">
            <div className="holding-pl">
              <strong className={tone(s.pl)}>{signedMoney(s.pl, c)}</strong>
              <span className={tone(s.pl_pct)}>{pct(s.pl_pct)}</span>
            </div>
            {s.advice && <p className={`advice ${s.advice.level}`}>{s.advice.text}</p>}
          </div>
          <div className="stats stats-wide">
            <div className="stat"><span className="stat-label">Bestand</span><strong className="stat-value">{qty(s.shares)} Stück</strong></div>
            <div className="stat"><span className="stat-label">Ø Kaufkurs</span><strong className="stat-value">{money(s.avg_price, c)}</strong></div>
            <div className="stat"><span className="stat-label">Aktuell</span><strong className="stat-value">{money(s.price, c)}</strong></div>
            <div className="stat"><span className="stat-label">Eingesetzt</span><strong className="stat-value">{money(s.invested, c)}</strong></div>
            <div className="stat"><span className="stat-label">Wert</span><strong className="stat-value">{money(s.value, c)}</strong></div>
            {s.closed_lots > 0 && <div className={`stat ${tone(s.realized)}`}><span className="stat-label">Realisiert</span><strong className="stat-value">{signedMoney(s.realized, c)}</strong></div>}
          </div>
          {s.avg_price && <RiskBar entry={s.avg_price} stop={s.stop} target={s.target} current={s.price} currency={c} />}
          {s.mixed_currency && <p className="muted small">Käufe in verschiedenen Währungen – Summen siehe einzelne Käufe.</p>}
        </>
      ) : (
        <p className="muted">Kein offener Bestand. Realisiert: <strong className={tone(s.realized)}>{signedMoney(s.realized, c)}</strong></p>
      )}

      <div className="table-wrap lots">
        <table className="table">
          <thead>
            <tr><th>Kauf</th><th className="num">Stück</th><th className="num">Kurs</th><th className="num hide-sm">Stopp / Ziel</th><th className="num">Ergebnis</th><th /></tr>
          </thead>
          <tbody>
            {open.map((p) => (
              <tr key={p.id}>
                <td>{date(p.buy_date)}{p.note && <div className="muted small">„{p.note}“</div>}
                  {p.hints?.filter((h) => h.suggested_stop || h.level === "bad").map((h) => (
                    <div key={h.text} className={`small hint-inline ${h.level}`}>
                      {h.text}
                      {h.suggested_stop && <button className="link small" onClick={() => act(() => api.patch(`/positions/${p.id}`, { stop: h.suggested_stop }))}>übernehmen</button>}
                    </div>
                  ))}
                </td>
                <td className="num">{qty(p.quantity)}</td>
                <td className="num">{money(p.buy_price, p.display_currency)}</td>
                <td className="num hide-sm muted small">{money(p.stop, p.display_currency)} / {money(p.target, p.display_currency)}</td>
                <td className={`num ${tone(p.pl)}`}>{signedMoney(p.pl, p.display_currency)}<div className="small">{pct(p.pl_pct)}</div></td>
                <td className="row-actions">
                  <button className="link small" onClick={() => setDialog({ mode: "sell", pos: p })}>Verkauf</button>
                  <button className="link small" onClick={() => setDialog({ mode: "edit", pos: p })}>Bearbeiten</button>
                </td>
              </tr>
            ))}
            {closed.map((p) => (
              <tr key={p.id} className="inactive">
                <td>{date(p.buy_date)} – {date(p.sell_date)}<div className="muted small">verkauft</div></td>
                <td className="num">{qty(p.quantity)}</td>
                <td className="num">{money(p.buy_price, p.display_currency)} → {money(p.sell_price, p.display_currency)}</td>
                <td className="num hide-sm" />
                <td className={`num ${tone(p.pl)}`}>{signedMoney(p.pl, p.display_currency)}<div className="small">{pct(p.pl_pct)}</div></td>
                <td className="row-actions">
                  <button className="link small" onClick={() => act(() => api.patch(`/positions/${p.id}`, { reopen: true }))}>Wieder öffnen</button>
                  <button className="link danger small" onClick={() => window.confirm("Verkauften Kauf löschen?") && act(() => api.del(`/positions/${p.id}`))}>Löschen</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {dialog && <EditDialog pos={dialog.pos} mode={dialog.mode} onClose={() => setDialog(null)} onSaved={onChanged} />}
    </section>
  );
}
