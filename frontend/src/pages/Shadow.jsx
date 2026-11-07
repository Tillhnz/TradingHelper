import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import AssetRow from "../components/AssetRow.jsx";
import DepotTabs from "../components/DepotTabs.jsx";
import PnlChart from "../components/PnlChart.jsx";
import { Empty, ErrorText, Loading } from "../components/ui.jsx";
import { dateTime, money, num, pct, signedMoney, tone } from "../fmt.js";
import { displayName } from "../texts.js";

const ORDER_STATUS = { open: "wartet", filled: "ausgeführt", cancelled: "verfallen" };
const day = (d) => (d ? new Date(d).toLocaleDateString("de-DE") : "–");
const shares = (n) => num(n, n % 1 ? 4 : 0);

function Backtest({ onApplied }) {
  const [bt, setBt] = useState(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(() => api.get("/paper/backtest").then(setBt).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (bt?.status !== "running") return undefined;
    const t = setTimeout(load, 2500);
    return () => clearTimeout(t);
  }, [bt, load]);

  async function start() {
    setError("");
    try { setBt({ ...(await api.post("/paper/backtest")), result: bt?.result }); } catch (e) { setError(e.message); }
  }

  async function apply(v) {
    try {
      await api.put("/settings", { invest_horizon: v.horizon, risk_profile: v.risk });
      setMsg(`Strategie auf „${v.label}“ umgestellt. Alle Empfehlungen und das Schattendepot richten sich ab jetzt danach.`);
      onApplied?.();
      load();
    } catch (e) { setError(e.message); }
  }

  const r = bt?.result;
  const lines = useMemo(() => (r ? [
    { points: r.curves.current, color: "#f2b84b", title: "Deine" },
    { points: r.curves.benchmark, color: "#8d9eb0", title: "Halten", dashed: true },
  ] : null), [r]);
  const names = r?.names || {};
  const running = bt?.status === "running";
  const best = r?.variants.find((v) => v.horizon === r.best.horizon && v.risk === r.best.risk);

  return (
    <section className="panel" id="rueckblick">
      <div className="panel-head">
        <h2>Rückblick: Welche Strategie hätte am meisten gebracht?</h2>
        <button className="btn small" onClick={start} disabled={running}>{running ? "Rechne …" : r ? "Neu rechnen" : "Rückblick starten"}</button>
      </div>
      <p className="muted small">
        Dieselben Kauf- und Verkaufsregeln laufen über die letzten zwei Jahre deiner Watchlist – für alle neun Kombinationen
        aus Anlagehorizont und Risikobereitschaft. Im <strong>Lernjahr</strong> wird die beste Variante ermittelt, im
        <strong> Prüfjahr</strong> zeigt sich, ob sie auch auf Kursen gut ist, nach denen sie nicht ausgesucht wurde. So fällt
        Glück nicht als Können durch. Läuft automatisch jeden Sonntag neu.
      </p>
      <ErrorText error={error || (bt?.status === "error" && bt.error)} />
      {msg && <p className="ok" role="status">{msg}</p>}
      {running && (
        <>
          <div className="progress" aria-label="Fortschritt"><span style={{ width: `${Math.round((bt.progress || 0) * 100)}%` }} /></div>
          <p className="muted small">Lade fünf Jahre Kurse und spiele jeden Handelstag durch – das dauert je nach Anzahl der Werte ein bis fünf Minuten.</p>
        </>
      )}
      {!bt && <Loading />}
      {bt && !r && !running && <p className="muted">Noch kein Rückblick gerechnet.</p>}
      {r && (
        <>
          <div className={`verdict-box v-${r.verdict}`}>
            <p>{r.text}</p>
            {r.verdict === "switch" && best && !best.current && (
              <div className="actions"><button className="btn small primary" onClick={() => apply(best)}>„{best.label}“ übernehmen</button></div>
            )}
          </div>
          <p className="muted small">
            Lernjahr {day(r.learn.from)} – {day(r.learn.to)} · Prüfjahr {day(r.test.from)} – {day(r.test.to)} ·
            Start je {money(r.capital, r.currency)} · {money(r.fee, r.currency)} pro Order · gerechnet {dateTime(r.created)}
          </p>
          <div className="table-wrap">
            <table className="table compact">
              <thead>
                <tr>
                  <th>Strategie</th>
                  <th className="num">Lernjahr</th>
                  <th className="num">Prüfjahr</th>
                  <th className="num hide-sm">größter Einbruch</th>
                  <th className="num hide-sm">Verkäufe</th>
                  <th className="num hide-sm">Treffer</th>
                  <th className="hide-sm" />
                </tr>
              </thead>
              <tbody>
                {r.variants.map((v, i) => (
                  <tr key={v.label} className={`${v.current ? "is-current" : ""} ${i === 0 ? "is-best" : ""}`}>
                    <td>{v.label}{v.current && <span className="tag cur">deine</span>}{i === 0 && <span className="tag best">Lern-Sieger</span>}</td>
                    <td className={`num ${tone(v.learn.return_pct)}`}>{pct(v.learn.return_pct, 1)}</td>
                    <td className={`num ${tone(v.test.return_pct)}`}><strong>{pct(v.test.return_pct, 1)}</strong></td>
                    <td className="num hide-sm neg">{pct(v.test.max_drawdown_pct, 1)}</td>
                    <td className="num hide-sm">{v.test.trades}</td>
                    <td className="num hide-sm">{v.test.win_rate == null ? "–" : `${num(v.test.win_rate, 0)} %`}</td>
                    <td className="row-actions hide-sm">{!v.current && <button className="link small" onClick={() => apply(v)}>übernehmen</button>}</td>
                  </tr>
                ))}
                <tr>
                  <td className="muted">Alles kaufen und halten</td>
                  <td className={`num ${tone(r.benchmark.learn.return_pct)}`}>{pct(r.benchmark.learn.return_pct, 1)}</td>
                  <td className={`num ${tone(r.benchmark.test.return_pct)}`}>{pct(r.benchmark.test.return_pct, 1)}</td>
                  <td className="num hide-sm neg">{pct(r.benchmark.test.max_drawdown_pct, 1)}</td>
                  <td className="hide-sm" /><td className="hide-sm" /><td className="hide-sm" />
                </tr>
              </tbody>
            </table>
          </div>
          <h3 className="sub-title">Prüfjahr im Verlauf</h3>
          <PnlChart points={r.curves.best} lines={lines} height={240} />
          <div className="legend small muted">
            <span style={{ "--c": "#6fd3c3" }}>Lern-Sieger ({r.best.label})</span>
            <span style={{ "--c": "#f2b84b" }}>deine Strategie</span>
            <span style={{ "--c": "#8d9eb0" }}>kaufen und halten</span>
          </div>
          {r.best_trades?.length > 0 && (
            <details className="details">
              <summary>Orders des Lern-Siegers im Prüfjahr ({r.best_trades.length})</summary>
              <TradeTable trades={r.best_trades.map((t) => ({ ...t, name: names[t.symbol] }))} currency={r.currency} />
            </details>
          )}
          {Object.keys(r.skipped || {}).length > 0 && (
            <p className="muted small">Nicht berücksichtigt: {Object.entries(r.skipped).map(([k, v]) => `${k} (${v})`).join(", ")}</p>
          )}
          <p className="muted small">
            Ehrlich gesagt: Der Rückblick kennt keine alten Nachrichten und bewertet nur die Technik. Gute Ergebnisse in der
            Vergangenheit sind keine Garantie – bei wenigen Werten und nur zwei Jahren spielt Zufall eine große Rolle.
          </p>
        </>
      )}
    </section>
  );
}

function TradeTable({ trades, currency }) {
  return (
    <div className="table-wrap">
      <table className="table compact">
        <thead><tr><th>Datum</th><th>Wert</th><th className="num">Stück × Kurs</th><th className="num">Ergebnis</th><th className="hide-sm">Grund</th></tr></thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={t.id ?? `${t.day}-${t.symbol}-${i}`}>
              <td className="small">{day(t.day)}<div className={t.side === "buy" ? "side-buy" : "side-sell"}>{t.side === "buy" ? "Kauf" : "Verkauf"}</div></td>
              <td>
                <Link className="sym" to={`/chart/${encodeURIComponent(t.symbol)}`}>{displayName(t)}</Link>
                <div className="muted small show-sm-block reason">{t.reason}</div>
              </td>
              <td className="num small">{shares(t.shares)} × {money(t.price, currency)}</td>
              <td className={`num ${tone(t.pl)}`}>{t.pl == null ? <span className="muted">–</span> : <>{signedMoney(t.pl, currency)}<div className="small">{pct(t.pl_pct, 1)}</div></>}</td>
              <td className="hide-sm muted small reason">{t.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Shadow() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await api.get("/paper"));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function run() {
    setBusy(true);
    setMsg("");
    setError("");
    try {
      const r = await api.post("/paper/run");
      const n = r.trades.length, o = r.orders?.length || 0;
      setMsg(n || o ? [n ? `${n} ${n === 1 ? "Order" : "Orders"} ausgeführt` : "", o ? `${o} ${o === 1 ? "Order" : "Orders"} platziert (Börse geschlossen)` : ""].filter(Boolean).join(", ") + "."
        : "Alles geprüft – gerade keine Kauf- oder Verkaufssignale.");
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    if (!window.confirm("Schattendepot komplett zurücksetzen? Alle virtuellen Positionen und Orders werden gelöscht.")) return;
    await api.post("/paper/reset").catch((e) => setError(e.message));
    setMsg("");
    load();
  }

  const c = data?.currency;
  const curve = data?.curve || [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Schattendepot</h1>
          <p className="muted">Ein virtuelles Depot, das die Einschätzungen von TradeHelper automatisch mit Spielgeld handelt. So siehst du, ob die Regeln in der Praxis Geld verdienen – ohne echtes Risiko.</p>
        </div>
      </div>
      <DepotTabs />
      <ErrorText error={error} />
      {msg && <p className="ok" role="status">{msg}</p>}
      {!data && !error && <Loading />}

      {data && !data.started && (
        <Empty title="Noch nicht gestartet">
          <p className="muted">
            Startkapital {money(data.capital, "EUR")}, {money(data.fee, "EUR")} Gebühr pro Order. Gekauft wird, wenn ein Wert deiner
            Watchlist auf „Gute Gelegenheit“ steht – mit der Positionsgröße deiner Risikobereitschaft. Verkauft wird am Stopp
            (der mit dem Kurs nachgezogen wird), am Kursziel oder wenn die Einschätzung auf „Vorsicht“ kippt.
          </p>
          <button className="btn primary" onClick={run} disabled={busy}>{busy ? "Prüfe alle Werte …" : `Mit ${money(data.capital, "EUR")} starten`}</button>
        </Empty>
      )}

      {data?.started && (
        <>
          <div className="shadow-bar">
            <span className="muted small grow">
              Läuft seit {day(data.started)}
              {data.enabled
                ? <> · handelt mit jedem Bericht{data.trade_times?.length ? ` (${data.trade_times.join(" und ")} Uhr)` : ""}{data.next_run ? `, nächster Lauf ${dateTime(data.next_run)}` : ""}</>
                : <> · <strong>automatischer Handel ausgeschaltet</strong></>}
              {data.last_run && <> · zuletzt {dateTime(data.last_run)}</>}
            </span>
            <button className="btn small primary" onClick={run} disabled={busy}>{busy ? "Prüfe …" : "Jetzt prüfen und handeln"}</button>
            <Link className="link small" to="/settings#paper">Einstellungen</Link>
          </div>

          <div className="hero-total">
            <span className="label">Wert des Schattendepots</span>
            <span className="big">{money(data.value, c)}</span>
            <strong className={tone(data.pl)}>{signedMoney(data.pl, c)} · {pct(data.pl_pct, 1)}</strong>
            <span className="sub">
              Kaufen und halten: <span className={tone(data.benchmark_pct)}>{pct(data.benchmark_pct, 1)}</span>
              {" · "}freies Geld {money(data.cash, c)}
              {" · "}{data.trades_count} Verkäufe{data.win_rate != null ? `, ${num(data.win_rate, 0)} % mit Gewinn` : ""}
            </span>
          </div>

          {curve.length > 1 ? (
            <section className="panel chart-panel">
              <div className="panel-head"><h2>Verlauf</h2><span className="muted small">Gewinn/Verlust gegenüber dem Startkapital</span></div>
              <PnlChart points={curve} />
            </section>
          ) : (
            <p className="note small">Der Verlauf erscheint ab dem zweiten Handelstag. Aussagekräftig wird das Schattendepot erst nach einigen Wochen und vielen Orders – für eine schnelle Einschätzung gibt es unten den Rückblick.</p>
          )}

          <div className="list-head"><h2>Offene Positionen</h2><span className="muted small">{data.positions.length}</span></div>
          {data.positions.length ? (
            <ul className="asset-list">
              {data.positions.map((p) => (
                <AssetRow key={p.symbol} symbol={p.symbol} name={displayName(p)}
                  meta={<>{shares(p.shares)} Stück · seit {day(p.entry_day)} · Kauf {money(p.entry, c)}</>}
                  top={{ text: money(p.value, c) }} bottom={{ text: `${signedMoney(p.pl, c)} · ${pct(p.pl_pct, 1)}`, tone: tone(p.pl) }}
                  hint={{ level: "info", text: `Stopp ${money(p.stop, c)}${p.target ? ` · Ziel ${money(p.target, c)}` : ""}` }} />
              ))}
            </ul>
          ) : <p className="calm-note">Gerade nichts im Schattendepot – kein Wert deiner Watchlist steht auf „Gute Gelegenheit“.</p>}

          {data.orders?.length > 0 && (
            <>
              <h2 className="section-title">Platzierte Orders</h2>
              <p className="muted small">Bei geschlossener Börse legt das Schattendepot Orders an. Sie werden während der Handelszeit alle 10 Minuten geprüft; Kauf-Limits gelten bis Handelsende.</p>
              <ul className="order-list">
                {data.orders.slice(0, 12).map((o) => (
                  <li key={o.id} className={`order-${o.status}`}>
                    <span className={o.side === "buy" ? "side-buy" : "side-sell"}>{o.side === "buy" ? "Kauf" : "Verkauf"}</span>
                    <Link className="sym" to={`/chart/${encodeURIComponent(o.symbol)}`}>{displayName(o)}</Link>
                    <span className="small">{o.side === "buy" ? `Limit ${money(o.limit_price, c)}` : "zur Eröffnung"}</span>
                    <span className={`order-status small ${o.status}`}>{ORDER_STATUS[o.status]}{o.note ? ` · ${o.note}` : ""}</span>
                    <span className="muted small">{day(o.day)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          <h2 className="section-title">Ausgeführt</h2>
          {data.trades.length ? <TradeTable trades={data.trades} currency={c} /> : <p className="muted">Noch keine Orders.</p>}
        </>
      )}

      {data && <div className="section-gap" />}
      {data && <Backtest onApplied={load} />}

      {data?.started && (
        <p className="small"><button className="link danger small" onClick={reset}>Schattendepot zurücksetzen und neu starten</button></p>
      )}
    </>
  );
}
