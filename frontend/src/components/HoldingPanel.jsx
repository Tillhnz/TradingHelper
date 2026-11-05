import { useState } from "react";
import { api } from "../api.js";
import { money, num, pct, signedMoney, tone } from "../fmt.js";
import { RiskBar } from "./BuyDialog.jsx";
import EditDialog from "./EditDialog.jsx";
import Term from "./Term.jsx";

const date = (iso) => (iso ? new Date(iso).toLocaleDateString("de-DE") : "–");
const qty = (q) => num(q, q % 1 ? 3 : 0);

/** Zwei Kacheln wie im Kauf-Dialog: was du bis zum Stopp verlieren und bis zum Ziel gewinnen kannst – ab jetzt. */
function RiskChance({ s, c }) {
  const stopHit = s.risk_to_stop != null && s.risk_to_stop < 0;
  return (
    <div className="riskchance">
      <div className={`stat ${s.risk_to_stop == null ? "" : "neg"}`}>
        <span className="stat-label"><Term name="Stopp">Risiko bis Stopp</Term></span>
        <strong className="stat-value">
          {s.risk_to_stop == null ? "kein Stopp" : stopHit ? "Stopp unterschritten" : `−${money(s.risk_to_stop, c)}`}
        </strong>
        {s.pl_at_stop != null && <span className="small muted">Ergebnis dann {signedMoney(s.pl_at_stop, c)}</span>}
        {s.lots_without_stop > 0 && s.risk_to_stop != null && <span className="small warn">{s.lots_without_stop} Kauf ohne Stopp</span>}
      </div>
      <div className={`stat ${s.chance_to_target == null ? "" : "pos"}`}>
        <span className="stat-label"><Term name="Ziel">Chance bis Ziel</Term></span>
        <strong className="stat-value">
          {s.chance_to_target == null ? "kein Ziel" : s.chance_to_target <= 0 ? "Ziel erreicht" : `+${money(s.chance_to_target, c)}`}
        </strong>
        {s.pl_at_target != null && <span className="small muted">Ergebnis dann {signedMoney(s.pl_at_target, c)}</span>}
      </div>
      {s.risk_to_stop > 0 && s.chance_to_target > 0 && (
        <div className="stat">
          <span className="stat-label"><Term name="Chance/Risiko" /></span>
          <strong className="stat-value">{(s.chance_to_target / s.risk_to_stop).toFixed(1).replace(".", ",")}</strong>
          <span className="small muted">ab aktuellem Kurs</span>
        </div>
      )}
    </div>
  );
}

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

  const remove = (p) => {
    if (window.confirm(`Kauf vom ${date(p.buy_date)} (${qty(p.quantity)} Stück) löschen? Das lässt sich nicht rückgängig machen.`)) {
      act(() => api.del(`/positions/${p.id}`));
    }
  };

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
          <RiskChance s={s} c={c} />
          {s.avg_price && <RiskBar entry={s.avg_price} stop={s.stop} target={s.target} current={s.price} currency={c} />}
          <div className="stats stats-wide">
            <div className="stat"><span className="stat-label">Bestand</span><strong className="stat-value">{qty(s.shares)} Stück</strong></div>
            <div className="stat"><span className="stat-label">{s.lots > 1 ? "Erster Kauf" : "Gekauft am"}</span><strong className="stat-value">{date(s.since)}</strong>
              {s.lots > 1 && <span className="small muted">{s.lots} Käufe</span>}</div>
            <div className="stat"><span className="stat-label">Ø Kaufkurs</span><strong className="stat-value">{money(s.avg_price, c)}</strong></div>
            <div className="stat"><span className="stat-label">Aktuell</span><strong className="stat-value">{money(s.price, c)}</strong></div>
            <div className="stat"><span className="stat-label">Eingesetzt</span><strong className="stat-value">{money(s.invested, c)}</strong></div>
            <div className="stat"><span className="stat-label">Wert</span><strong className="stat-value">{money(s.value, c)}</strong></div>
            {s.closed_lots > 0 && <div className={`stat ${tone(s.realized)}`}><span className="stat-label">Realisiert</span><strong className="stat-value">{signedMoney(s.realized, c)}</strong></div>}
          </div>
          {s.mixed_currency && <p className="muted small">Käufe in verschiedenen Währungen – Summen siehe einzelne Käufe.</p>}
        </>
      ) : (
        <p className="muted">Kein offener Bestand. Realisiert: <strong className={tone(s.realized)}>{signedMoney(s.realized, c)}</strong></p>
      )}

      <h3 className="sub-title lots-title">Deine Käufe</h3>
      <ul className="lots">
        {open.map((p) => (
          <li key={p.id} className="lot">
            <div className="lot-main">
              <strong>{date(p.buy_date)} · {qty(p.quantity)} Stück à {money(p.buy_price, p.display_currency)}</strong>
              {p.note && <span className="muted small">„{p.note}“</span>}
              <span className="muted small">
                Stopp {money(p.stop, p.display_currency)}{p.trail_pct ? ` (läuft ${String(p.trail_pct).replace(".", ",")} % unter dem Hoch mit)` : ""} · Ziel {money(p.target, p.display_currency)}
              </span>
              {p.hints?.filter((h) => h.suggested_stop || h.suggested_target || h.level === "bad" || h.text.startsWith("Stopp läuft")).map((h) => (
                <span key={h.text} className={`small hint-inline ${h.level}`}>
                  {h.text}
                  {h.suggested_stop && <button className="link small" onClick={() => act(() => api.patch(`/positions/${p.id}`, { stop: h.suggested_stop }))}>übernehmen</button>}
                  {h.suggested_target && <button className="link small" onClick={() => act(() => api.patch(`/positions/${p.id}`, { target: h.suggested_target }))}>Ziel übernehmen</button>}
                </span>
              ))}
              {!p.trail_pct && p.trail_suggest_pct && (
                <span className="small muted">
                  Tipp: Stopp mitlaufen lassen ({String(p.trail_suggest_pct).replace(".", ",")} % passend zu deiner Strategie){" "}
                  <button className="link small" onClick={() => act(() => api.patch(`/positions/${p.id}`, { trail_pct: p.trail_suggest_pct }))}>einschalten</button>
                </span>
              )}
            </div>
            <div className={`lot-pl ${tone(p.pl)}`}>
              <strong>{signedMoney(p.pl, p.display_currency)}</strong>
              <span className="small">{pct(p.pl_pct)}</span>
            </div>
            <div className="lot-actions">
              <button className="btn small" onClick={() => setDialog({ mode: "sell", pos: p })}>Verkauf erfassen</button>
              <button className="btn small" onClick={() => setDialog({ mode: "edit", pos: p })}>Bearbeiten</button>
              <button className="btn small danger" onClick={() => remove(p)}>Löschen</button>
            </div>
          </li>
        ))}
        {closed.map((p) => (
          <li key={p.id} className="lot closed">
            <div className="lot-main">
              <strong>{qty(p.quantity)} Stück · {money(p.buy_price, p.display_currency)} → {money(p.sell_price, p.display_currency)}</strong>
              <span className="muted small">verkauft · {date(p.buy_date)} – {date(p.sell_date)}</span>
            </div>
            <div className={`lot-pl ${tone(p.pl)}`}>
              <strong>{signedMoney(p.pl, p.display_currency)}</strong>
              <span className="small">{pct(p.pl_pct)}</span>
            </div>
            <div className="lot-actions">
              <button className="btn small" onClick={() => act(() => api.patch(`/positions/${p.id}`, { reopen: true }))}>Wieder öffnen</button>
              <button className="btn small danger" onClick={() => remove(p)}>Löschen</button>
            </div>
          </li>
        ))}
      </ul>
      {error && <p className="error" role="alert">{error}</p>}
      {dialog && <EditDialog pos={dialog.pos} mode={dialog.mode} onClose={() => setDialog(null)} onSaved={onChanged} />}
    </section>
  );
}
