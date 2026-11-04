import { useState } from "react";
import { Link } from "react-router-dom";
import { dateTime } from "../fmt.js";
import { displayName } from "../texts.js";

export function ago(iso) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const min = Math.round((Date.now() - t) / 60000);
  if (min < 1) return "gerade eben";
  if (min < 60) return `vor ${min} Min.`;
  const h = Math.round(min / 60);
  if (h < 24) return `vor ${h} Std.`;
  const d = Math.round(h / 24);
  return d === 1 ? "gestern" : d < 7 ? `vor ${d} Tagen` : dateTime(iso);
}

function Mood({ v }) {
  if (v > 0.15) return <span className="mood pos" title="Schlagzeile klingt positiv">▲ positiv</span>;
  if (v < -0.15) return <span className="mood neg" title="Schlagzeile klingt negativ">▼ negativ</span>;
  return null;
}

/** Nachrichtenliste mit Quelle, Zeit und Stimmung. showStock: Name des Werts als Link davor. */
export default function NewsList({ items, initial = 6, showStock = false, empty }) {
  const [all, setAll] = useState(false);
  if (!items?.length) return empty ? <p className="muted">{empty}</p> : null;
  const shown = all ? items : items.slice(0, initial);
  return (
    <>
      <ul className="news-list">
        {shown.map((n) => (
          <li key={`${n.symbol || ""}${n.url || n.headline}`}>
            <div className="news-meta small">
              {showStock && n.symbol && (
                <Link className="news-stock" to={`/chart/${encodeURIComponent(n.symbol)}`}>{displayName(n)}</Link>
              )}
              <span className="news-src">{n.source || n.via}</span>
              <span className="muted" title={dateTime(n.published)}>{ago(n.published)}</span>
              <Mood v={n.sentiment} />
            </div>
            <a className="news-head" href={n.url} target="_blank" rel="noreferrer noopener">{n.headline}</a>
            {n.summary && <p className="news-sum muted small">{n.summary}</p>}
          </li>
        ))}
      </ul>
      {items.length > initial && (
        <button className="link small news-more" onClick={() => setAll((a) => !a)}>
          {all ? "Weniger anzeigen" : `Alle ${items.length} Meldungen anzeigen`}
        </button>
      )}
    </>
  );
}
