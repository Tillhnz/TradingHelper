import { Link } from "react-router-dom";
import { useCachedGet } from "../cache.js";
import { ago } from "./NewsList.jsx";
import Icon from "./Icon.jsx";
import { DriverBar, ProbBar } from "./viz.jsx";
import { num } from "../fmt.js";
import { ACTION_UI } from "../texts.js";

/** Einschätzung des lernenden Modells für einen Wert, mit Begründung und wie sie mit den Regeln kombiniert wird. */
export function ModelCard({ model }) {
  if (!model) {
    return (
      <section className="panel" id="modell">
        <div className="panel-head"><h2><Icon name="brain" className="h-icon" /> Modell</h2><Link className="link small" to="/modell">So lernt es</Link></div>
        <p className="muted small" style={{ margin: 0 }}>Für diesen Wert gibt es noch keine Vorhersage – sie kommt mit dem nächsten Lernlauf.</p>
      </section>
    );
  }
  const w = model.weight || 0;
  const fin = model.final || {};
  return (
    <section className="panel" id="modell">
      <div className="panel-head">
        <h2><Icon name="brain" className="h-icon" /> Modell</h2>
        <span className={`model-chip ${ACTION_UI[model.action]?.tone || ""}`}>{ACTION_UI[model.action]?.label}</span>
      </div>
      <p className="small" style={{ marginTop: 0 }}>In den nächsten {model.days} Handelstagen:</p>
      <ProbBar p={model} />
      {model.drivers?.length > 0 && (
        <>
          <p className="muted small" style={{ margin: "0.9rem 0 0.35rem" }}>Was die Einschätzung treibt (← fallen · steigen →)</p>
          <ul className="drivers">
            {model.drivers.map((d) => <li key={d.group}><span>{d.text}</span><DriverBar delta={d.delta} /></li>)}
          </ul>
        </>
      )}
      <p className="muted small" style={{ margin: "0.9rem 0 0" }}>
        {w > 0
          ? <>Zählt zu {Math.round(w * 100)} % neben den Regeln ({ACTION_UI[model.rule?.action]?.short}) → zusammen: <strong>{ACTION_UI[fin.action]?.label}</strong>. Käufe brauchen immer auch die Regeln.</>
          : <>Das Modell war auf ungesehenen Daten zuletzt nicht besser als der Zufall – es wird angezeigt, zählt aber nicht.</>}
      </p>
    </section>
  );
}

/** Was im Netz über den Wert gesagt wird. */
export function SocialCard({ symbol }) {
  const q = useCachedGet(`/social/${encodeURIComponent(symbol)}`, { pollWhile: (d) => d?.refreshing && !d?.data, every: 4000, maxPolls: 6 });
  const s = q.data?.data;
  if (q.data && !q.data.enabled) return null;
  return (
    <section className="panel" id="stimmung">
      <div className="panel-head">
        <h2><Icon name="message" className="h-icon" /> Stimmung im Netz</h2>
        {s?.fetched && <span className="muted small">{ago(new Date(s.fetched * 1000).toISOString())}</span>}
      </div>
      {!s ? <p className="muted small" style={{ margin: 0 }}>{q.data?.refreshing ? "Sammle Beiträge aus StockTwits, Bluesky, Reddit und Wikipedia …" : "Noch keine Daten."}</p> : (
        <>
          <div className="kpi-row" style={{ gap: "1rem 2rem" }}>
            <div><span className="kpi-label">Stimmung</span><span className={`kpi-small ${s.score > 0.15 ? "pos" : s.score < -0.15 ? "neg" : ""}`}>
              {s.score == null ? "–" : s.score > 0.15 ? "positiv" : s.score < -0.15 ? "negativ" : "neutral"}</span></div>
            <div><span className="kpi-label">Beiträge</span><span className="kpi-small">{s.n || 0}</span></div>
            {s.bull_ratio != null && <div><span className="kpi-label">bullish</span><span className="kpi-small">{Math.round(s.bull_ratio * 100)} %</span></div>}
            {s.buzz != null && <div><span className="kpi-label">Buzz (24 h vs. Woche)</span><span className="kpi-small">{num(s.buzz, 1)}×</span></div>}
            {s.attention && <div><span className="kpi-label">Wikipedia-Aufrufe</span><span className="kpi-small">{num(s.attention.ratio, 1)}×</span></div>}
          </div>
          {s.samples?.length > 0 && (
            <ul className="posts" style={{ marginTop: "0.9rem" }}>
              {s.samples.slice(0, 6).map((p) => (
                <li key={p.url || p.text} className={p.sentiment > 0.15 ? "p" : p.sentiment < -0.15 ? "n" : ""}>
                  {p.url ? <a href={p.url} target="_blank" rel="noreferrer noopener">{p.text}</a> : p.text}
                  <div className="src">{p.source}{p.time ? ` · ${ago(p.time)}` : ""}</div>
                </li>
              ))}
            </ul>
          )}
          <p className="muted small" style={{ margin: "0.75rem 0 0" }}>Quellen: {Object.keys(s.sources || {}).filter((k) => !s.sources[k].error).join(", ") || "–"}{s.attention ? ", Wikipedia" : ""}</p>
        </>
      )}
    </section>
  );
}
