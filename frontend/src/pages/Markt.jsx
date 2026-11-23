import { Link } from "react-router-dom";
import { useCachedGet } from "../cache.js";
import Icon from "../components/Icon.jsx";
import { Loading, RefreshState } from "../components/ui.jsx";
import { Gauge, LineArea, Spark } from "../components/viz.jsx";
import { num, pct, tone } from "../fmt.js";
import { MacroList, Regime } from "../widgets/index.jsx";

const GROUPS = ["Zinsen", "Preise", "Konjunktur", "Stimmung", "Risiko"];

/** Markt: Indizes und Rohstoffe, Konjunktur weltweit/Euroraum/Deutschland/USA, Stimmung an der Börse und im Netz. */
export default function Markt() {
  const mk = useCachedGet("/markets");
  const mac = useCachedGet("/macro");
  const mood = useCachedGet("/mood");
  const ind = mac.data?.indicators || [];
  const fg = mood.data?.fear_greed;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Markt</h1>
          <p className="muted">Das Umfeld, in dem deine Werte sich bewegen – und aus dem das Modell lernt. <RefreshState q={mk} /></p>
        </div>
      </div>

      <section className="panel">
        <div className="panel-head"><h2>Märkte</h2></div>
        {!mk.data ? <Loading /> : (
          <div className="mkt-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(170px, 1fr))" }}>
            {mk.data.items.map((m) => (
              <Link key={m.symbol} to={`/chart/${encodeURIComponent(m.symbol)}`} className="mkt" style={{ textDecoration: "none", color: "inherit" }}>
                <span className="lbl">{m.label}</span>
                <span className="val">{m.price == null ? "–" : num(m.price, m.price > 1000 ? 0 : 2)}</span>
                <span className={`small delta ${tone(m.change_pct)}`}>{pct(m.change_pct)}</span>
                <Spark values={m.spark} height={26} />
              </Link>
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-head"><h2>Konjunktur</h2><span className="muted small">{mac.data?.sources?.slice(0, 4).join(" · ")}</span></div>
        {!mac.data ? <Loading /> : (
          <>
            <Regime r={mac.data.regime} />
            {ind.length === 0 && <p className="muted">Die Zahlen werden gerade zum ersten Mal geladen (alle 6 Stunden aktualisiert).</p>}
            <div className="macro-groups" style={{ marginTop: "1rem" }}>
              {GROUPS.map((g) => {
                const items = ind.filter((i) => i.group === g);
                if (!items.length) return null;
                return (
                  <div key={g}>
                    <h3 style={{ margin: "0 0 0.3rem" }}>{g}</h3>
                    <MacroList items={items} />
                  </div>
                );
              })}
            </div>
            <p className="muted small" style={{ marginTop: "1rem" }}>Grün/Rot zeigt, ob die Veränderung der letzten drei Monate für Aktien eher Rückenwind
              (z. B. sinkende Inflation, steigende Stimmung) oder Gegenwind ist. Das Modell nutzt jede Zahl erst ab dem Tag, an dem sie veröffentlicht wurde.</p>
          </>
        )}
      </section>

      <section className="panel">
        <div className="panel-head"><h2>Stimmung</h2></div>
        {!mood.data ? <Loading /> : (
          <div className="pf-head" style={{ marginBottom: 0 }}>
            <div>
              <h3 style={{ margin: "0 0 0.5rem" }}>An der Börse (CNN Fear & Greed)</h3>
              {fg ? (
                <>
                  <Gauge value={fg.score} label={fg.label} sub={`vor einer Woche ${fg.previous_week != null ? Math.round(fg.previous_week) : "–"} · vor einem Monat ${fg.previous_month != null ? Math.round(fg.previous_month) : "–"}`} />
                  <div style={{ marginTop: "0.75rem" }}><LineArea values={fg.spark} height={70} tone="accent" /></div>
                </>
              ) : <p className="muted">Noch nicht geladen.</p>}
            </div>
            <div>
              <h3 style={{ margin: "0 0 0.5rem" }}>Im Netz zu deinen Werten</h3>
              {mood.data.items.length ? (
                <ul className="mini-list">
                  {mood.data.items.slice(0, 10).map((x) => (
                    <li key={x.symbol}>
                      <Link to={`/chart/${encodeURIComponent(x.symbol)}#stimmung`} className="two"><span className="nm">{x.name || x.symbol}</span>
                        <span className="sub">{x.n} Beiträge{x.bull_ratio != null ? ` · ${Math.round(x.bull_ratio * 100)} % bullish` : ""}{x.buzz ? ` · Buzz ${num(x.buzz, 1)}×` : ""}{x.attention ? ` · Wikipedia ${num(x.attention, 1)}×` : ""}</span></Link>
                      <span className={`rt ${tone(x.score)}`}>{x.score == null ? "–" : x.score > 0.15 ? "positiv" : x.score < -0.15 ? "negativ" : "neutral"}</span>
                    </li>
                  ))}
                </ul>
              ) : <p className="muted small"><Icon name="info" /> Stimmung aus StockTwits, Bluesky, Reddit und Wikipedia-Aufrufen wird alle 30 Minuten für deine Werte gesammelt. Zugangsdaten: Einstellungen → Datenquellen.</p>}
            </div>
          </div>
        )}
      </section>
    </>
  );
}
