import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import BuyDialog, { RiskBar } from "../components/BuyDialog.jsx";
import DepotTabs from "../components/DepotTabs.jsx";
import EditDialog from "../components/EditDialog.jsx";
import PnlChart from "../components/PnlChart.jsx";
import { ActionBadge, Empty, ErrorText, Loading, Stat } from "../components/ui.jsx";
import { money, num, pct, signedMoney, tone } from "../fmt.js";
import { displayName, displayTicker } from "../texts.js";

export default function Depot() {
  const [data, setData] = useState(null);
  const [hist, setHist] = useState(null);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState(null); // {mode, pos}

  const load = useCallback(async () => {
    try {
      const [d, h] = await Promise.all([api.get("/positions"), api.get("/positions/history")]);
      setData(d);
      setHist(h);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function applyStop(pos, value) {
    try {
      await api.patch(`/positions/${pos.id}`, { stop: value });
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function remove(pos) {
    if (!window.confirm(`Position ${pos.symbol} vom ${pos.buy_date} löschen?`)) return;
    await api.del(`/positions/${pos.id}`).catch((e) => setError(e.message));
    load();
  }

  async function reopen(pos) {
    await api.patch(`/positions/${pos.id}`, { reopen: true }).catch((e) => setError(e.message));
    load();
  }

  const open = data?.items.filter((p) => !p.closed) || [];
  const closed = data?.items.filter((p) => p.closed) || [];
  const t = data?.totals;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Depot</h1>
          <p className="muted">Erfasste Käufe mit Gewinn und Verlust, Hinweisen zu Stopp und Ziel.</p>
        </div>
        <button className="btn primary" onClick={() => setDialog({ mode: "buy" })}>Kauf erfassen</button>
      </div>
      <DepotTabs />
      <ErrorText error={error} />
      {!data && !error && <Loading />}

      {data && !data.items.length && (
        <Empty title="Noch keine Käufe erfasst">
          <p className="muted">Erfasse einen Kauf hier oder direkt im Chart. Danach siehst du Gewinn- und Verlustzone im Chart und hier den Verlauf.</p>
          <button className="btn primary" onClick={() => setDialog({ mode: "buy" })}>Ersten Kauf erfassen</button>
        </Empty>
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="stats stats-wide totals">
            <Stat label="Eingesetzt (offen)" value={money(t.invested, t.currency)} />
            <Stat label="Aktueller Wert" value={money(t.value, t.currency)} />
            <Stat label="Gewinn/Verlust offen" value={signedMoney(t.pl, t.currency)} className={tone(t.pl)} />
            <Stat label="in Prozent" value={pct(t.pl_pct)} className={tone(t.pl_pct)} />
            <Stat label="Realisiert" value={signedMoney(t.realized, t.currency)} className={tone(t.realized)} />
          </div>

          {hist?.points?.length > 1 && (
            <section className="panel chart-panel">
              <div className="panel-head"><h2>Verlauf Gewinn/Verlust</h2><span className="muted small">in {hist.currency}, offene und realisierte Positionen</span></div>
              <PnlChart points={hist.points} />
            </section>
          )}

          {open.length > 0 && (
            <>
              <h2 className="section-title">Offene Positionen</h2>
              <div className="positions">
                {open.map((p) => {
                  const c = p.display_currency;
                  return (
                    <article key={p.id} className={`position ${p.pl > 0 ? "gain" : p.pl < 0 ? "loss" : ""}`}>
                      <header>
                        <Link className="sym" to={`/chart/${encodeURIComponent(p.symbol)}`}>{displayName(p)}</Link>
                        <span className="muted small">{displayTicker(p)} · {num(p.quantity, p.quantity % 1 ? 3 : 0)} Stück · seit {new Date(p.buy_date).toLocaleDateString("de-DE")}</span>
                        <ActionBadge action={p.action} held />
                      </header>
                      {p.error ? <p className="error small">{p.error}</p> : (
                        <>
                          <div className="position-pl">
                            <strong className={tone(p.pl)}>{signedMoney(p.pl, c)}</strong>
                            <span className={tone(p.pl_pct)}>{pct(p.pl_pct)}</span>
                          </div>
                          <p className="muted small">Kauf {money(p.buy_price, c)} · jetzt {money(p.price, c)} · Wert {money(p.value, c)}</p>
                          <RiskBar entry={p.buy_price} stop={p.stop} target={p.target} current={p.price} currency={c} />
                          {(p.risk_to_stop != null || p.chance_to_target != null) && (
                            <p className="small riskline">
                              {p.risk_to_stop != null && <span className="neg">bis Stopp {p.risk_to_stop < 0 ? "unterschritten" : `−${money(p.risk_to_stop, c)}`}</span>}
                              {p.chance_to_target != null && <span className="pos">bis Ziel {p.chance_to_target <= 0 ? "erreicht" : `+${money(p.chance_to_target, c)}`}</span>}
                            </p>
                          )}
                        </>
                      )}
                      {p.hints?.length > 0 && (
                        <ul className="hints">
                          {p.hints.map((h) => (
                            <li key={h.text} className={h.level}>
                              {h.text}
                              {h.suggested_stop && <button className="link small" onClick={() => applyStop(p, h.suggested_stop)}>übernehmen</button>}
                            </li>
                          ))}
                        </ul>
                      )}
                      {p.note && <p className="muted small">„{p.note}“</p>}
                      <div className="actions">
                        <button className="btn small" onClick={() => setDialog({ mode: "sell", pos: p })}>Verkauf erfassen</button>
                        <button className="btn small" onClick={() => setDialog({ mode: "edit", pos: p })}>Bearbeiten</button>
                        <button className="link danger small" onClick={() => remove(p)}>Löschen</button>
                      </div>
                    </article>
                  );
                })}
              </div>
            </>
          )}

          {closed.length > 0 && (
            <>
              <h2 className="section-title">Abgeschlossen</h2>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Wert</th><th className="hide-sm">Zeitraum</th><th className="num">Kauf</th><th className="num">Verkauf</th><th className="num">Ergebnis</th><th /></tr></thead>
                  <tbody>
                    {closed.map((p) => (
                      <tr key={p.id}>
                        <td><Link className="sym" to={`/chart/${encodeURIComponent(p.symbol)}`}>{displayName(p)}</Link><div className="muted small">{num(p.quantity, p.quantity % 1 ? 3 : 0)} Stück</div></td>
                        <td className="hide-sm muted small">{new Date(p.buy_date).toLocaleDateString("de-DE")} – {new Date(p.sell_date).toLocaleDateString("de-DE")}</td>
                        <td className="num">{money(p.buy_price, p.display_currency)}</td>
                        <td className="num">{money(p.sell_price, p.display_currency)}</td>
                        <td className={`num ${tone(p.pl)}`}>{signedMoney(p.pl, p.display_currency)}<div className="small">{pct(p.pl_pct)}</div></td>
                        <td className="row-actions">
                          <button className="link small" onClick={() => reopen(p)}>Wieder öffnen</button>
                          <button className="link danger small" onClick={() => remove(p)}>Löschen</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      {dialog?.mode === "buy" && <BuyDialog onClose={() => setDialog(null)} onSaved={load} />}
      {dialog && dialog.mode !== "buy" && <EditDialog pos={dialog.pos} mode={dialog.mode} onClose={() => setDialog(null)} onSaved={load} />}
    </>
  );
}
