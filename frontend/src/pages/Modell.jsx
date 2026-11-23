import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { useCachedGet } from "../cache.js";
import Icon from "../components/Icon.jsx";
import { ErrorText, Loading } from "../components/ui.jsx";
import { Spark } from "../components/viz.jsx";
import { dateTime, num, pct, tone } from "../fmt.js";
import { ACTION_UI } from "../texts.js";

const HZ = { short: "Kurzfristig (5 Tage)", medium: "Mittelfristig (20 Tage)", long: "Langfristig (60 Tage)" };
const GROUP_TEXT = { Technik: "Kursverlauf & Indikatoren", Markt: "Marktumfeld", Makro: "Konjunktur", Stimmung: "News & soziale Netzwerke" };
const p100 = (x) => (x == null ? "–" : `${Math.round(x * 100)} %`);

function Horizon({ id, h }) {
  const s = h.summary || {};
  const groups = h.folds?.[0]?.groups || {};
  const maxG = Math.max(0.01, ...Object.values(groups).map((v) => Math.max(0, v)));
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{HZ[id]}</h2>
        <span className="muted small">Version {h.version} · gelernt aus {num(h.rows, 0)} Tagen von {h.symbols} Werten ({h.from?.slice(0, 4)}–{h.to?.slice(0, 4)})</span>
      </div>
      <div className="score-cmp">
        <div><span className="kpi-label">Können auf ungesehenen Daten</span><span className="kpi-small">{p100(h.skill)}</span>
          <div className="muted small">{h.skill > 0 ? "besser als die Basisrate" : "nicht besser als die Basisrate – nur Regeln zählen"}</div></div>
        <div><span className="kpi-label">Gewicht neben den Regeln</span><span className="kpi-small">{p100(h.weight)}</span>
          <div className="muted small">aus Können × Bilanz im Journal</div></div>
        <div><span className="kpi-label">Trefferquote (Prüfzeiträume)</span><span className="kpi-small">{p100(s.accuracy)}</span>
          <div className="muted small">Basisrate {p100(s.accuracy_base)} · Vorteil {s.edge == null ? "–" : `${num(s.edge, 2)} %-Pkt.`}</div></div>
      </div>

      <h3 style={{ margin: "1.25rem 0 0.4rem" }}>Welche Daten gerade helfen</h3>
      <p className="muted small" style={{ marginTop: 0 }}>Wie viel schlechter das Modell wird, wenn man eine Datengruppe durcheinanderwürfelt.</p>
      <ul className="drivers">
        {Object.entries(groups).sort((a, b) => b[1] - a[1]).map(([g, v]) => (
          <li key={g} style={{ gridTemplateColumns: "minmax(0, 1fr) 40%" }}>
            <span>{GROUP_TEXT[g] || g} {h.feature_coverage?.[g] != null && h.feature_coverage[g] < 0.5 && <span className="muted small">(erst {p100(h.feature_coverage[g])} Daten)</span>}</span>
            <span className="ibar"><span style={{ width: `${Math.max(2, (Math.max(0, v) / maxG) * 100)}%`, opacity: v > 0 ? 1 : 0.25 }} /></span>
          </li>
        ))}
      </ul>

      <h3 style={{ margin: "1.25rem 0 0.4rem" }}>Varianten im Vergleich</h3>
      <div className="table-wrap">
        <table className="table fold-table">
          <thead><tr><th>Variante</th><th className="num">Logloss-Gewinn</th><th className="num">Vorteil</th><th className="num">Treffer</th></tr></thead>
          <tbody>
            {Object.entries(h.candidates || {}).map(([k, c]) => (
              <tr key={k}><td>{k}{k === h.config && <span className="badge buy" style={{ marginLeft: "0.4rem" }}>gewählt</span>}</td>
                <td className={`num ${tone(c.gain)}`}>{c.gain == null ? "–" : num(c.gain, 4)}</td>
                <td className={`num ${tone(c.edge)}`}>{c.edge == null ? "–" : `${num(c.edge, 2)} %`}</td>
                <td className="num">{p100(c.accuracy)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 style={{ margin: "1.25rem 0 0.4rem" }}>Prüfung auf späteren Zeiträumen</h3>
      <div className="table-wrap">
        <table className="table fold-table">
          <thead><tr><th>Zeitraum</th><th className="num">Treffer</th><th className="num">„Verkaufen“ lag richtig</th><th className="num">vermiedener Verlust</th><th className="num">„Kaufen“ lag richtig</th><th className="num">Vorteil</th></tr></thead>
          <tbody>
            {(h.folds || []).map((f) => (
              <tr key={f.test_from}><td>{f.test_from?.split("-").reverse().join(".")} – {f.test_to?.split("-").reverse().join(".")}</td>
                <td className="num">{p100(f.accuracy)} <span className="muted small">/ {p100(f.accuracy_base)}</span></td>
                <td className="num">{p100(f.sell_hit)} <span className="muted small">({f.sell_signals})</span></td>
                <td className={`num ${tone(f.sell_avoided)}`}>{f.sell_avoided == null ? "–" : `${num(f.sell_avoided, 1)} %`}</td>
                <td className="num">{p100(f.buy_hit)} <span className="muted small">({f.buy_signals})</span></td>
                <td className={`num ${tone(f.edge)}`}>{num(f.edge, 2)} %</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      {h.history?.length > 1 && (
        <p className="muted small" style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>Können über die letzten Trainings:
          <span style={{ width: 160 }}><Spark values={h.history.map((x) => x.skill)} height={24} /></span></p>
      )}
      {h.track?.n > 0 && (
        <>
          <h3 style={{ margin: "1.25rem 0 0.4rem" }}>Bilanz im Entscheidungsjournal ({h.track.n} bewertet)</h3>
          <div className="score-cmp">
            <div><span className="kpi-label">Regeln</span><span className="kpi-small">{p100(h.track.rule_acc)}</span></div>
            <div><span className="kpi-label">Modell</span><span className="kpi-small">{p100(h.track.model_acc)}</span></div>
            <div><span className="kpi-label">Kombiniert</span><span className="kpi-small">{p100(h.track.final_acc)}</span></div>
          </div>
          <p className="muted small">„Verkaufen wäre besser gewesen“: {h.track.sell_better}× · „Halten wäre besser gewesen“: {h.track.hold_better}×</p>
        </>
      )}
    </section>
  );
}

/** Wie das Modell lernt, wie gut es ist und was es aus seinen Fehlern mitnimmt. */
export default function Modell({ user }) {
  const q = useCachedGet("/model");
  const d = q.data;
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!status?.running) return undefined;
    const id = setInterval(() => api.get("/model/status").then((s) => { setStatus(s); if (!s.running) q.reload(); }).catch(() => {}), 2000);
    return () => clearInterval(id);
  }, [status?.running]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (d?.status) setStatus(d.status); }, [d]);

  async function train() {
    setError("");
    try { await api.post("/model/train"); setStatus({ running: true, step: "Start", progress: 0 }); } catch (e) { setError(e.message); }
  }
  const hz = Object.entries(d?.horizons || {});

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Lernendes Modell</h1>
          <p className="muted">Lernt jede Nacht aus Kursen, Marktumfeld, Konjunktur und Stimmung – und rechnet jede eigene Einschätzung nach.</p>
        </div>
        {user?.is_admin && <button className="btn" onClick={train} disabled={status?.running}><Icon name="brain" /> {status?.running ? "Lernt …" : "Jetzt neu lernen"}</button>}
      </div>
      <ErrorText error={error || q.error} />
      {status?.running && (
        <div className="panel"><p style={{ marginTop: 0 }}>{status.step}</p><div className="progress-line"><span style={{ width: `${Math.round((status.progress || 0) * 100)}%` }} /></div></div>
      )}
      {status?.error && <p className="error">Letztes Training: {status.error}</p>}
      {!d && !q.error && <Loading />}
      {d && !hz.length && (
        <div className="empty">
          <h3>Noch nicht gelernt</h3>
          <p className="muted">Der erste Lauf passiert heute Nacht automatisch{user?.is_admin ? " – oder jetzt über „Jetzt neu lernen“" : ""}. Beim ersten Mal lädt er fünf Jahre Kursgeschichte für rund 60 Werte; das dauert einige Minuten.</p>
        </div>
      )}
      {hz.map(([id, h]) => <Horizon key={id} id={id} h={h} />)}

      {d && (
        <section className="panel">
          <div className="panel-head"><h2>Entscheidungsjournal</h2><span className="muted small">nachgerechnet nach Ablauf des Horizonts</span></div>
          {!d.journal.length ? <p className="muted">Die ersten Urteile gibt es, sobald die ersten Einschätzungen ihren Horizont erreicht haben (kurzfristig nach einer Woche).</p> : (
            <ul className="verdict-list">
              {d.journal.map((j) => {
                const good = /^Richtig|^Vertretbar|^Kaum/.test(j.verdict || "");
                return (
                  <li key={j.id}>
                    <span className={`vmark ${good ? "ok" : "bad"}`} />
                    <span><Link to={`/chart/${encodeURIComponent(j.symbol)}`} style={{ color: "inherit", textDecoration: "none" }}><strong>{j.name || j.symbol.replace(/\.GTX$/, "")}</strong></Link>
                      <span className="muted small"> · {j.day.split("-").reverse().join(".")} · {HZ[j.horizon]?.split(" ")[0]} · Regeln: {ACTION_UI[j.rule_action]?.short || "–"}{j.model_action ? ` · Modell: ${ACTION_UI[j.model_action]?.short}` : ""}</span></span>
                    <span className={`small ${tone(j.outcome)}`}>{pct((j.outcome || 0) * 100, 1)}</span>
                    <span className="vd">{j.verdict}{j.lesson ? ` – ${j.lesson}` : ""}</span>
                  </li>
                );
              })}
            </ul>
          )}
          {d.open?.length > 0 && <p className="muted small" style={{ marginTop: "0.75rem" }}>{d.open.length}+ Einschätzungen warten noch auf ihr Urteil (zuletzt {dateTime(d.open[0].day).split(",")[0]}).</p>}
        </section>
      )}

      <section className="panel">
        <h2>So funktioniert es</h2>
        <ol className="small" style={{ paddingLeft: "1.1rem", margin: 0, display: "grid", gap: "0.35rem" }}>
          <li><strong>Lernen:</strong> Für jeden Tag der letzten Jahre und rund 60 Werte (plus deine) wird festgehalten, was man an dem Tag wissen konnte – und was danach passiert ist: deutlich gefallen, seitwärts oder gestiegen.</li>
          <li><strong>Selbst prüfen:</strong> Mehrere Varianten lernen nur aus der Vergangenheit und werden auf den jeweils folgenden drei Monaten geprüft. Die beste gewinnt. Ist keine besser als die Basisrate, hat das Modell kein Gewicht.</li>
          <li><strong>Hinterfragen:</strong> Jede tägliche Einschätzung kommt ins Journal und wird nach Ablauf des Horizonts nachgerechnet („Verkaufen wäre besser gewesen“). Fehlentscheidungen zählen beim nächsten Lernen doppelt, und wer öfter recht hatte – Regeln oder Modell –, bekommt mehr Gewicht.</li>
          <li><strong>Vorsicht eingebaut:</strong> Die Wahrscheinlichkeiten werden zur Basisrate hin gezogen, so stark wie es die letzte Prüfung verlangt. Einen Kauf darf das Modell nie allein auslösen – nur bremsen oder vor einem Rückgang warnen.</li>
        </ol>
      </section>
    </>
  );
}
