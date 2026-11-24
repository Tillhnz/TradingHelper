import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useCachedGet } from "../cache.js";
import CompareChart from "../components/CompareChart.jsx";
import Icon from "../components/Icon.jsx";
import { ErrorText, Loading, RefreshState } from "../components/ui.jsx";
import { money, num, pct, signedMoney, tone } from "../fmt.js";
import { C, SERIES } from "../theme.js";

/* Analyse der eigenen Anlagestrategie: Wie gut ist meine Rendite (IZF, zeitgewichtet), wie schlage ich mich
   gegen Indizes, und wie handle ich (Trefferquote, Haltedauer, Timing, Gebühren, Streuung)? */

const pending = (d) => !!(d && (d.pending || d.refreshing));
const HORIZON = { short: "kurzfristig", medium: "mittelfristig", long: "langfristig" };
const LEVEL_ICON = { good: "check", warn: "alert", bad: "alert", info: "info" };
const days = (d) => (d == null ? "–" : `${num(d, 0)} ${d === 1 ? "Tag" : "Tage"}`);
const benchColor = (i) => SERIES[(i + 1) % SERIES.length]; // feste Reihenfolge, Depot hat die erste Farbe

function Kpi({ label, value, sub, valueTone = "", hint }) {
  return (
    <div className="an-kpi" title={hint}>
      <span className="an-kpi-label">{label}{hint && <Icon name="info" />}</span>
      <strong className={`an-kpi-value ${valueTone}`}>{value}</strong>
      {sub && <span className="an-kpi-sub">{sub}</span>}
    </div>
  );
}

function Fact({ label, value, note, valueTone = "" }) {
  return (
    <div className="an-fact">
      <span className="an-fact-label">{label}</span>
      <strong className={valueTone}>{value}</strong>
      {note && <span className="an-fact-note">{note}</span>}
    </div>
  );
}

function Months({ months }) {
  if (!months?.length) return null;
  const max = Math.max(...months.map((m) => Math.abs(m.pct || 0)), 1);
  return (
    <div className="an-months" role="img" aria-label="Monatsrenditen">
      {months.map((m) => {
        const h = Math.max(2, (Math.abs(m.pct || 0) / max) * 50);
        const [y, mo] = m.month.split("-");
        const label = new Date(+y, +mo - 1, 1).toLocaleDateString("de-DE", { month: "short", year: "2-digit" });
        return (
          <div key={m.month} className="an-month" title={`${label}: ${pct(m.pct, 1)}`}>
            <span className={`bar ${m.pct >= 0 ? "pos" : "neg"}`} style={{ height: `${h}%`, [m.pct >= 0 ? "bottom" : "top"]: "50%" }} />
            <span className="lbl">{mo === "01" || months.length <= 12 ? label : ""}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function Analyse() {
  const q = useCachedGet("/strategy", { pollWhile: pending, every: 2500, maxPolls: 30 });
  const a = q.data;
  const [mode, setMode] = useState("index");
  const [shown, setShown] = useState(() => new Set(["EUNL.DE", "EXS1.DE"]));
  const [busy, setBusy] = useState(false);
  const ccy = a?.currency || "EUR";

  const series = useMemo(() => {
    if (!a?.curve) return [];
    const out = mode === "index"
      ? [{ id: "pf", label: "Dein Depot", color: C.accent, values: a.curve.portfolio, width: 3 }]
      : [{ id: "pf", label: "Dein Depot", color: C.accent, values: a.curve.value, width: 3 },
        { id: "inv", label: "Eingezahlt", color: C.neutral, values: a.curve.invested, dashed: true, width: 1 }];
    (a.benchmarks || []).forEach((b, i) => {
      if (!shown.has(b.symbol)) return;
      const values = mode === "index" ? a.curve[b.symbol] : a.curve[`${b.symbol}:value`];
      if (values) out.push({ id: b.symbol, label: b.label, color: benchColor(i), values });
    });
    return out;
  }, [a, mode, shown]);

  async function recompute() {
    setBusy(true);
    try { q.set(await api.get("/strategy?refresh=true&budget=6")); } catch { q.reload(); } finally { setBusy(false); }
  }
  const toggle = (sym) => setShown((s) => { const n = new Set(s); if (n.has(sym)) n.delete(sym); else n.add(sym); return n; });

  const b = a?.behavior || {};
  const world = a?.benchmarks?.find((x) => x.symbol === "EUNL.DE");
  const short = (a?.period?.days || 0) < 365;
  const irrOf = (x) => (short ? x.irr_period : x.irr);
  const generated = a?.generated_at ? new Date(a.generated_at * 1000) : null;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Analyse</h1>
          <p className="muted">Wie gut ist deine Strategie? Rendite, Vergleich mit Indizes und wie du handelst – aus all deinen Käufen und Verkäufen.</p>
          <p className="muted small" style={{ margin: 0 }}>
            {generated && <span className="freshness">Berechnet {generated.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })} Uhr mit Tagesschlusskursen{a.period ? ` · Zeitraum ${new Date(a.period.from).toLocaleDateString("de-DE")} – ${new Date(a.period.to).toLocaleDateString("de-DE")}` : ""}</span>}
            {" "}<RefreshState q={q} />{a?.refreshing && <span className="refresh-state"><span className="spinner" aria-hidden="true" /> rechnet neu …</span>}
          </p>
        </div>
        {a && !a.empty && !a.pending && <button className="btn" onClick={recompute} disabled={busy}><Icon name="refresh" /> {busy ? "Rechne …" : "Neu berechnen"}</button>}
      </div>
      <ErrorText error={q.error || a?.error} />
      {(!a || a.pending) && !q.error && <Loading text="Rechne deine Rendite und die Vergleichsdepots durch … (beim ersten Mal einige Sekunden)" />}

      {a?.empty && (
        <section className="panel">
          <h2>Noch nichts zu analysieren</h2>
          <p className="muted">Für die Analyse braucht es Käufe mit Datum. Lade unter <Link to="/portfolio">Portfolio</Link> deine Umsätze (CSV) oder Abrechnungen (PDF) hoch oder erfasse Käufe unter <Link to="/depot">Käufe & Blöcke</Link>.</p>
          {a.undated_holdings > 0 && <p className="muted small">{a.undated_holdings} Bestände aus Depotauszügen haben kein Kaufdatum und zählen deshalb nicht mit.</p>}
        </section>
      )}

      {a && !a.empty && !a.pending && !a.error && a.period && (
        <>
          <section className="an-kpis">
            {short ? (
              <Kpi label="Interner Zinsfuß (IZF)" value={`${pct(a.irr_period, 1)}`} valueTone={tone(a.irr_period)}
                sub={`im Zeitraum (${a.period.days} Tage) · hochgerechnet ${pct(a.irr, 0)} p. a.${world?.irr_period != null ? ` · MSCI World: ${pct(world.irr_period, 1)}` : ""}`}
                hint="Geldgewichtete Rendite: berücksichtigt, wann wie viel Geld investiert war. Unter einem Jahr zeigen wir sie für den Zeitraum – hochgerechnet aufs Jahr wirkt sie sonst riesig." />
            ) : (
              <Kpi label="Interner Zinsfuß (IZF)" value={a.irr != null ? `${pct(a.irr, 1)} p. a.` : "–"} valueTone={tone(a.irr)}
                sub={world?.irr != null ? `MSCI World mit gleichem Geld: ${pct(world.irr, 1)} p. a.` : null}
                hint="Geldgewichtete Rendite pro Jahr: berücksichtigt, wann wie viel Geld investiert war – deine persönliche Rendite." />
            )}
            <Kpi label="Zeitgewichtete Rendite" value={pct(a.twr, 1)} valueTone={tone(a.twr)}
              sub={a.twr_pa != null ? `${pct(a.twr_pa, 1)} pro Jahr` : `seit ${new Date(a.period.from).toLocaleDateString("de-DE")}`}
              hint="Rendite der Auswahl, unabhängig davon, wann Geld dazukam – so rechnen Fonds. Gut zum Vergleich mit Indizes." />
            <Kpi label="Gewinn gesamt" value={signedMoney(a.gain, ccy)} valueTone={tone(a.gain)}
              sub={`${pct(a.gain_pct, 1)} auf max. ${money(a.peak_capital, ccy)} Einsatz`}
              hint="Heutiger Wert + Verkaufserlöse − alle Käufe (inkl. Gebühren)." />
            <Kpi label="Größter Rückgang" value={a.max_drawdown != null ? pct(a.max_drawdown, 1) : "–"} valueTone={a.max_drawdown < -15 ? "neg" : ""}
              sub={a.drawdown_from && a.max_drawdown < 0 ? `${new Date(a.drawdown_from).toLocaleDateString("de-DE")} – ${new Date(a.drawdown_to).toLocaleDateString("de-DE")}` : "vom Hoch bis zum Tief"}
              hint="Maximaler Wertverlust vom bisherigen Höchststand (zeitgewichtet)." />
            <Kpi label="Schwankung" value={a.volatility != null ? `${num(a.volatility, 1)} %` : "–"} sub="pro Jahr (Volatilität)"
              hint="Standardabweichung der Tagesrenditen, aufs Jahr hochgerechnet. MSCI World: meist 12–18 %." />
            <Kpi label="Gebühren" value={money(a.fees, ccy)} sub={b.fees_pct != null ? `${num(b.fees_pct, 2)} % vom Handelsvolumen` : null} />
          </section>

          {a.insights?.length > 0 && (
            <section className="panel">
              <h2 className="section-title" style={{ marginTop: 0 }}>Was auffällt</h2>
              <ul className="an-insights">
                {a.insights.map((t) => (
                  <li key={t.title} className={`lvl-${t.level}`}>
                    <Icon name={LEVEL_ICON[t.level] || "info"} />
                    <div><strong>{t.title}</strong><p>{t.text}</p></div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {a.checks?.length > 0 && (
            <section className="panel" id="datenpruefung">
              <h2 className="section-title" style={{ marginTop: 0 }}>Datenprüfung</h2>
              <p className="muted small" style={{ marginTop: 0 }}>Diese Einträge passen nicht zu den Marktdaten. Korrigiere sie unter <Link to="/depot">Käufe & Blöcke</Link> – danach rechnet die Analyse automatisch neu.</p>
              <ul className="an-insights">
                {a.checks.map((c, i) => (
                  <li key={`${c.symbol}-${c.day}-${i}`} className={`lvl-${c.level}`}>
                    <Icon name={LEVEL_ICON[c.level] || "info"} />
                    <div><strong><Link to={`/chart/${encodeURIComponent(c.symbol)}`}>{c.name}</Link></strong><p>{c.text}</p></div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="panel">
            <div className="section-row">
              <h2 className="section-title" style={{ marginTop: 0 }}>Gegen die Indizes</h2>
              <div className="seg" role="group" aria-label="Darstellung">
                <button className={mode === "index" ? "on" : ""} onClick={() => setMode("index")} title="Zeitgewichtete Rendite, Start = 0 %">Rendite</button>
                <button className={mode === "value" ? "on" : ""} onClick={() => setMode("value")} title="Was aus deinem Geld geworden wäre">Wert in {ccy}</button>
              </div>
            </div>
            <p className="muted small" style={{ marginTop: 0 }}>
              Jeder Vergleich ist ein Schattendepot: Es kauft mit <strong>genau deinen Beträgen an denselben Tagen</strong> einen
              thesaurierenden ETF auf den Index (inkl. Dividenden, in {ccy}) und verkauft jeweils denselben Anteil wie du.
            </p>
            <div className="chip-row">
              {(a.benchmarks || []).map((x, i) => (
                <button key={x.symbol} className={`chip ${shown.has(x.symbol) ? "on" : ""}`} onClick={() => toggle(x.symbol)} aria-pressed={shown.has(x.symbol)}>
                  <i style={{ background: benchColor(i) }} />{x.label}
                </button>
              ))}
            </div>
            {a.curve?.dates?.length > 1 && <CompareChart dates={a.curve.dates} series={series} mode={mode} currency={ccy} />}
            <div className="table-wrap" style={{ marginTop: "1rem" }}>
              <table className="table an-table">
                <thead>
                  <tr><th>Vergleich</th><th className="num" title="Wert heute + Verkaufserlöse − Käufe">Gewinn</th><th className="num">Unterschied zu dir</th><th className="num">{short ? "IZF im Zeitraum" : "IZF p. a."}</th>
                    <th className="num hide-sm">Zeitgewichtet</th><th className="num hide-sm" title="Wie stark dein Depot mit dem Index mitschwingt (1 = gleich stark)">Beta</th></tr>
                </thead>
                <tbody>
                  <tr className="me"><td><i className="sw" style={{ background: C.accent }} />Dein Depot</td><td className={`num ${tone(a.gain)}`}><strong>{signedMoney(a.gain, ccy)}</strong></td><td className="num">–</td>
                    <td className={`num ${tone(irrOf(a))}`}>{pct(irrOf(a), 1)}</td><td className={`num hide-sm ${tone(a.twr)}`}>{pct(a.twr, 1)}</td><td className="num hide-sm">1,00</td></tr>
                  {(a.benchmarks || []).map((x, i) => (
                    <tr key={x.symbol}>
                      <td><i className="sw" style={{ background: benchColor(i) }} />{x.label}<div className="acc-tag">{x.product} · {x.symbol}</div></td>
                      <td className={`num ${tone(x.gain)}`}>{signedMoney(x.gain, ccy)}</td>
                      <td className={`num ${tone(x.diff_value)}`}>{signedMoney(x.diff_value, ccy)}{x.diff_irr != null && !short && <div className="small">{x.diff_irr > 0 ? "+" : ""}{num(x.diff_irr, 1)} Pkt. p. a.</div>}</td>
                      <td className={`num ${tone(irrOf(x))}`}>{pct(irrOf(x), 1)}</td>
                      <td className={`num hide-sm ${tone(x.twr)}`}>{pct(x.twr, 1)}</td>
                      <td className="num hide-sm">{x.beta != null ? num(x.beta, 2) : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="muted small">Gewinn = Wert heute + Verkaufserlöse − Käufe. „Unterschied zu dir“: positiv = du liegst vorne. Verkaufst du, verkauft der Vergleich denselben Anteil. Zeitgewichtet zählt nur Tage, an denen du investiert warst.</p>
          </section>

          <section className="panel">
            <h2 className="section-title" style={{ marginTop: 0 }}>Wie du handelst</h2>
            <div className="an-facts">
              <Fact label="Käufe / Verkäufe" value={`${b.buys} / ${b.sells}`} note={`${num(b.buys_per_month, 1)} Käufe pro Monat · ${b.open} offen`} />
              <Fact label="Trefferquote" value={b.win_rate != null ? `${num(b.win_rate, 0)} %` : "–"} note={b.closed ? `${b.closed} abgeschlossene Trades` : "noch nichts verkauft"} />
              <Fact label="Ø Gewinn / Ø Verlust" value={<><span className="pos">{b.avg_win != null ? pct(b.avg_win, 1) : "–"}</span> / <span className="neg">{b.avg_loss != null ? pct(b.avg_loss, 1) : "–"}</span></>} note="je abgeschlossenem Trade" />
              <Fact label="Profit-Faktor" value={b.profit_factor != null ? num(b.profit_factor, 2) : "–"} valueTone={b.profit_factor == null ? "" : b.profit_factor >= 1 ? "pos" : "neg"} note={b.realized != null ? `realisiert ${signedMoney(b.realized, ccy)}` : "Gewinne ÷ Verluste"} />
              <Fact label="Haltedauer Gewinner" value={days(b.hold_win_days)} note="Median bis zum Verkauf" />
              <Fact label="Haltedauer Verlierer" value={days(b.hold_loss_days)} valueTone={b.hold_loss_days > (b.hold_win_days || 0) * 1.5 && b.hold_win_days ? "neg" : ""} note="länger als Gewinner = Dispositionseffekt" />
              <Fact label="Nach dem Verkauf" value={b.after_sell_pct != null ? pct(b.after_sell_pct, 1) : "–"} note={b.after_sell_n ? `Kurs 20 Handelstage später · ${b.sold_too_early}× > +5 % weitergelaufen` : "noch keine Daten"} />
              <Fact label="Nach dem Kauf" value={b.after_buy_pct != null ? pct(b.after_buy_pct, 1) : "–"} valueTone={tone(b.after_buy_pct)} note="Ø Kursänderung 20 Handelstage später" />
              <Fact label="Kaufkurs in der Jahresspanne" value={b.buy_range_pos != null ? `${num(b.buy_range_pos, 0)} %` : "–"} note="0 = Jahrestief, 100 = Jahreshoch" />
              <Fact label="Nachkäufe in Verluste" value={num(b.averaged_down ?? 0, 0)} note="> 3 % unter einem offenen Kauf" />
              <Fact label="Streuung" value={b.effective_n != null ? `${num(b.effective_n, 1)} Werte` : "–"} note={b.top_weight != null ? `größter: ${b.top_name} ${num(b.top_weight, 0)} %` : null} />
              <Fact label="Stopps gesetzt" value={b.with_stop_pct != null ? `${num(b.with_stop_pct, 0)} %` : "–"} note="der offenen Positionen" />
              {b.hold_median_days != null && (
                <Fact label="Haltedauer vs. Strategie" value={days(b.hold_median_days)} valueTone={b.horizon_fit === "passt" ? "pos" : ""}
                  note={<>eingestellt: {HORIZON[b.horizon]} · {b.horizon_fit === "passt" ? "passt" : <Link to="/settings">{b.horizon_fit} – anpassen</Link>}</>} />
              )}
            </div>
          </section>

          {a.months?.length > 1 && (
            <section className="panel">
              <h2 className="section-title" style={{ marginTop: 0 }}>Monatsrenditen</h2>
              <Months months={a.months} />
              <p className="muted small">Zeitgewichtet, letzte {a.months.length} Monate. Antippen bzw. darüberfahren zeigt den Wert.</p>
            </section>
          )}

          <div className="an-two">
            {a.positions?.length > 0 && (
              <section className="panel">
                <h2 className="section-title" style={{ marginTop: 0 }}>Beitrag je Wert</h2>
                <div className="table-wrap">
                  <table className="table">
                    <thead><tr><th>Wert</th><th className="num">Realisiert</th><th className="num">Offen</th><th className="num">Gesamt</th></tr></thead>
                    <tbody>
                      {a.positions.map((p) => (
                        <tr key={p.symbol}>
                          <td className="nm"><Link className="sym" to={`/chart/${encodeURIComponent(p.symbol)}`}>{p.name}</Link><div className="acc-tag">{p.trades} {p.trades === 1 ? "Kauf" : "Käufe"}</div></td>
                          <td className={`num ${tone(p.realized)}`}>{p.realized ? signedMoney(p.realized, ccy) : "–"}</td>
                          <td className={`num ${tone(p.open)}`}>{p.open ? signedMoney(p.open, ccy) : "–"}</td>
                          <td className={`num ${tone(p.total)}`}><strong>{signedMoney(p.total, ccy)}</strong><div className="small">{pct(p.pct, 1)}</div></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
            {a.years?.length > 0 && (
              <section className="panel">
                <h2 className="section-title" style={{ marginTop: 0 }}>Je Jahr</h2>
                <div className="table-wrap">
                  <table className="table">
                    <thead><tr><th>Jahr</th><th className="num">Käufe</th><th className="num">Investiert</th><th className="num">Verkäufe</th><th className="num">Realisiert</th></tr></thead>
                    <tbody>
                      {a.years.map((y) => (
                        <tr key={y.year}><td>{y.year}</td><td className="num">{y.buys}</td><td className="num">{money(y.invested, ccy)}</td><td className="num">{y.sells}</td>
                          <td className={`num ${tone(y.realized)}`}>{y.sells ? signedMoney(y.realized, ccy) : "–"}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="muted small">Realisiert vor Steuern. Für die Steuer zählen die Belege deiner Bank.</p>
              </section>
            )}
          </div>

          <details className="panel an-method">
            <summary>So wird gerechnet</summary>
            <ul className="small muted">
              <li><strong>IZF (interner Zinsfuß, XIRR):</strong> der Jahreszins, bei dem alle Käufe (Geld rein), Verkäufe (Geld raus) und der heutige Depotwert zusammen genau aufgehen. Er zeigt deine persönliche Rendite – auch das Timing deiner Einzahlungen zählt.</li>
              <li><strong>Zeitgewichtete Rendite:</strong> verkettet die täglichen Wertänderungen ohne Ein- und Auszahlungen. Sie misst die Qualität der Auswahl.</li>
              <li><strong>Vergleich:</strong> dieselben Kaufbeträge an denselben Tagen in iShares-ETFs (Xetra, thesaurierend); bei deinen Verkäufen verkauft der Vergleich denselben Anteil seines Bestands.</li>
              <li><strong>Zeitgewichtet:</strong> Käufe zählen zum Tagesbeginn, Verkaufserlöse zum Tagesende – so verzerren große Nachkäufe die Rendite nicht.</li>
              <li>Grundlage sind alle Käufe und Verkäufe mit Datum (auch importierte), bewertet mit Tagesschlusskursen in {ccy}; Fremdwährungen zum Tageskurs.{a.undated_holdings > 0 && ` ${a.undated_holdings} Bestände aus Depotauszügen ohne Kaufdatum zählen nicht mit.`}</li>
              {a.missing?.length > 0 && <li>Ohne Kurse (zum Einstand gezählt): {a.missing.join(", ")}.</li>}
            </ul>
          </details>
        </>
      )}
    </>
  );
}
