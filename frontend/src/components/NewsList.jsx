import { useMemo, useState } from "react";
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

const mood = (v) => (v > 0.15 ? "pos" : v < -0.15 ? "neg" : "neu");
const MOOD_LABEL = { pos: "klingt positiv", neg: "klingt negativ", neu: "neutral" };

const STOP = new Set(("aktie aktien der die das und mit für von auf den dem des ein eine im in ist zu nach bei über "
  + "the and for with from to of on in at is are as its by after stock stocks shares share inc corp ag se").split(" "));
const words = (s) => new Set((s.toLowerCase().match(/[a-zäöüß0-9]{3,}/g) || []).filter((w) => !STOP.has(w)));

/** Meldungen zum selben Thema bündeln (gleiche Kernwörter in der Schlagzeile, gleicher Wert). */
function group(items) {
  const groups = [];
  for (const n of items) {
    const w = words(n.headline);
    const hit = groups.find((g) => g.symbol === n.symbol && [...w].filter((x) => g.words.has(x)).length / Math.max(1, Math.min(w.size, g.words.size)) >= 0.6);
    if (hit) hit.more.push(n);
    else groups.push({ ...n, words: w, more: [] });
  }
  return groups;
}

const GERMAN = /[äöüß]|\b(der|die|das|und|nicht|mit|für|auf|aktie|kursziel|prozent)\b/i;

/**
 * Nachrichtenliste: oben die Stimmung auf einen Blick, darunter die Meldungen kompakt mit farbigem Rand
 * (grün positiv, rot negativ). Gleiche Themen aus mehreren Quellen werden zu einer Zeile gebündelt.
 */
export default function NewsList({ items, initial = 5, showStock = false, empty }) {
  const [all, setAll] = useState(false);
  const [lang, setLang] = useState("all");
  const [open, setOpen] = useState(null);

  const langs = useMemo(() => {
    const de = (items || []).filter((n) => GERMAN.test(n.headline)).length;
    return { de, en: (items || []).length - de };
  }, [items]);
  const filtered = useMemo(() => (items || []).filter((n) => lang === "all" || (lang === "de") === GERMAN.test(n.headline)), [items, lang]);
  const groups = useMemo(() => group(filtered), [filtered]);

  if (!items?.length) return empty ? <p className="muted">{empty}</p> : null;
  const counts = { pos: 0, neg: 0, neu: 0 };
  groups.forEach((g) => { counts[mood(g.sentiment)] += 1; });
  const total = groups.length || 1;
  const shown = all ? groups : groups.slice(0, initial);
  const decided = counts.pos + counts.neg;
  const overall = decided < total * 0.25 ? "eher neutral"
    : counts.pos > counts.neg * 1.5 ? "eher positiv" : counts.neg > counts.pos * 1.5 ? "eher negativ" : "gemischt";

  return (
    <>
      <div className="news-summary">
        <div className="mood-bar" aria-hidden="true">
          <span className="pos" style={{ width: `${(counts.pos / total) * 100}%` }} />
          <span className="neu" style={{ width: `${(counts.neu / total) * 100}%` }} />
          <span className="neg" style={{ width: `${(counts.neg / total) * 100}%` }} />
        </div>
        <p className="small">
          <strong>Stimmung {overall}</strong>
          <span className="muted"> · {groups.length} {groups.length === 1 ? "Thema" : "Themen"}: <span className="pos">{counts.pos} positiv</span>, <span className="neg">{counts.neg} negativ</span>, {counts.neu} neutral</span>
        </p>
        {langs.de > 0 && langs.en > 0 && (
          <div className="seg seg-small" role="group" aria-label="Sprache">
            {[["all", "Alle"], ["de", `Deutsch (${langs.de})`], ["en", `Englisch (${langs.en})`]].map(([id, label]) => (
              <button key={id} className={lang === id ? "on" : ""} onClick={() => { setLang(id); setAll(false); }}>{label}</button>
            ))}
          </div>
        )}
      </div>
      <ul className="news-list compact">
        {shown.map((n) => {
          const key = `${n.symbol || ""}${n.url || n.headline}`;
          const m = mood(n.sentiment);
          return (
            <li key={key} className={`mood-${m}`}>
              <a className="news-head" href={n.url} target="_blank" rel="noreferrer noopener">{n.headline}</a>
              <div className="news-meta small">
                {showStock && n.symbol && (
                  <Link className="news-stock" to={`/chart/${encodeURIComponent(n.symbol)}`}>{displayName(n)}</Link>
                )}
                <span className="news-src">{n.source || n.via}</span>
                <span className="muted" title={dateTime(n.published)}>{ago(n.published)}</span>
                {m !== "neu" && <span className={`mood-tag ${m}`}>{MOOD_LABEL[m]}</span>}
                {n.more.length > 0 && (
                  <button className="link small" onClick={() => setOpen(open === key ? null : key)} aria-expanded={open === key}>
                    +{n.more.length} {n.more.length === 1 ? "weitere Quelle" : "weitere Quellen"}
                  </button>
                )}
              </div>
              {open === key && (
                <ul className="news-more-list">
                  {n.more.map((x) => (
                    <li key={x.url || x.headline}>
                      <a href={x.url} target="_blank" rel="noreferrer noopener">{x.headline}</a>
                      <span className="muted small"> · {x.source || x.via} · {ago(x.published)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
      {groups.length > initial && (
        <button className="link small news-more" onClick={() => setAll((a) => !a)}>
          {all ? "Weniger anzeigen" : `Alle ${groups.length} Themen anzeigen`}
        </button>
      )}
    </>
  );
}
