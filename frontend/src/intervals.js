// Kerzenlängen für alle Charts (Seite eines Werts im Profi-Modus und großer Chart)
export const INTERVALS = [
  { id: "1s", label: "1s", title: "1 Sekunde" },
  { id: "1m", label: "1m", title: "1 Minute" },
  { id: "3m", label: "3m", title: "3 Minuten" },
  { id: "5m", label: "5m", title: "5 Minuten" },
  { id: "15m", label: "15m", title: "15 Minuten" },
  { id: "1h", label: "1h", title: "1 Stunde" },
  { id: "2h", label: "2h", title: "2 Stunden" },
  { id: "1d", label: "1T", title: "1 Tag" },
  { id: "1wk", label: "1W", title: "1 Woche" },
];
export const INTRADAY = new Set(["1s", "1m", "3m", "5m", "15m", "1h", "2h"]);
export const BAR_SECONDS = { "1s": 1, "1m": 60, "3m": 180, "5m": 300, "15m": 900, "1h": 3600, "2h": 7200 };
// Welche Zeiträume zu welcher Kerzenlänge passen (Yahoo liefert Minutenkerzen nur für die letzten Tage)
export const PERIODS_FOR = {
  "1s": ["1d"],
  "1m": ["1d", "5d"],
  "3m": ["1d", "5d"],
  "5m": ["1d", "5d", "1mo"],
  "15m": ["1d", "5d", "1mo"],
  "1h": ["5d", "1mo", "3mo", "6mo"],
  "2h": ["5d", "1mo", "3mo", "6mo"],
  "1d": ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
  "1wk": ["1y", "2y", "5y", "10y"],
};
export const PERIOD_LABEL = { "1d": "1 Tag", "5d": "5 Tage", "1mo": "1 Monat", "3mo": "3 Monate", "6mo": "6 Monate", "1y": "1 Jahr",
  "2y": "2 Jahre", "5y": "5 Jahre", "10y": "10 Jahre" };

/** Kerzenlängen, die für diesen Wert gehen: Sekundenkerzen nur für gettex (dort kommen sie aus den Einzelgeschäften). */
export function intervalsFor(meta) {
  const gettex = !!meta?.intraday_limit;
  return INTERVALS.filter((i) => (i.id !== "1s" || gettex) && (meta?.intraday !== false || !INTRADAY.has(i.id)));
}

/** Zeiträume für eine Kerzenlänge; gettex hat Minuten- und Sekundenkerzen nur für die letzten 5 Handelstage. */
export function periodsFor(interval, meta) {
  const list = PERIODS_FOR[interval] || PERIODS_FOR["1d"];
  if (meta?.intraday_limit && INTRADAY.has(interval)) return list.filter((p) => ["1d", "5d"].includes(p)).concat(list.includes("1d") || list.includes("5d") ? [] : ["5d"]);
  return list;
}

/** Beim Wechsel der Kerzenlänge einen passenden Zeitraum behalten oder wählen. */
export function pickPeriod(interval, current, meta) {
  const p = periodsFor(interval, meta);
  return p.includes(current) ? current : p[Math.min(1, p.length - 1)];
}
