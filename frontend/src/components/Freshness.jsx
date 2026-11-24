/* Von wann die Zahlen stammen – klein unter einem Baustein: „Kurse 14:32 Uhr · bis 15 Min. verzögert“,
   außerhalb der Handelszeit „Schlusskurse vom 21.11.“. */

function clock(d) {
  return d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
}

export function quoteStand(unix, { delay = null, prefix = "Kurse", dayOnly = false } = {}) {
  if (!unix) return "";
  const d = new Date(unix * 1000);
  if (dayOnly) return `Tageskurse vom ${d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })}`;
  const now = new Date();
  const ageH = (now - d) / 3600000;
  const sameDay = now.toDateString() === d.toDateString();
  const day = d.toLocaleDateString("de-DE", { weekday: ageH < 24 * 6 ? "short" : undefined, day: "2-digit", month: "2-digit" });
  let text;
  if (sameDay) text = `${prefix} von ${clock(d)} Uhr`;
  else if (ageH < 24 * 6) text = `Schlusskurse ${day}, ${clock(d)} Uhr`;
  else text = `${prefix} vom ${day}`;
  if (sameDay && ageH < 1 && delay) text += ` · bis ${delay} Min. verzögert`;
  else if (sameDay && ageH < 1 && delay === 0) text += " · Echtzeit";
  return text;
}

export default function Freshness({ asOf, oldest = null, delay = null, at = null, dayOnly = false, prefix = "Kurse", className = "" }) {
  const parts = [];
  if (asOf) parts.push(quoteStand(asOf, { delay, prefix, dayOnly }));
  if (asOf && oldest && asOf - oldest > 3 * 86400) parts.push("einzelne Werte älter");
  if (!asOf && at) {
    const d = new Date(at);
    const today = new Date().toDateString() === d.toDateString();
    parts.push(`Stand ${today ? "" : d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" }) + " "}${clock(d)} Uhr`);
  }
  if (!parts.length) return null;
  return <span className={`freshness ${className}`} title="Zeitpunkt der zugrunde liegenden Kurse">{parts.join(" · ")}</span>;
}

/** Jüngster Kurszeitpunkt einer Liste von Zeilen (Übersicht der Werte), live-Kurse eingeschlossen. */
export function latestTime(rows, quotes = {}) {
  let best = null;
  let day = null;
  let delay = null;
  (rows || []).forEach((r) => {
    const q = quotes[r.symbol];
    const t = (q && q.time) || r.quote_time;
    if (t && (!best || t > best)) best = t;
    if (r.as_of && (!day || r.as_of > day)) day = r.as_of;
    const dl = q?.delay_min ?? r.delay_min;
    if (dl != null) delay = Math.max(delay ?? 0, dl);
  });
  return best ? { asOf: best, delay } : { asOf: day, delay: null, dayOnly: !!day };
}
