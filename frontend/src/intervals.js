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

/* ---------- Zeitraum + Auflösung (kleiner und großer Chart) ----------
   Zeitraum = wie weit zurück; Auflösung = wie viel Zeit eine Kerze/ein Punkt zusammenfasst. Pro Zeitraum nur
   Auflösungen, die die Datenquellen liefern (Yahoo: Minuten nur für die letzten Wochen; gettex: Minuten und
   Sekunden nur für die letzten 5 Handelstage). */
export const RANGES = [
  { id: "1d", label: "Tag", period: "1d", res: ["1s", "1m", "3m", "5m", "15m", "1h"], def: "5m" },
  { id: "5d", label: "Woche", period: "5d", res: ["1m", "3m", "5m", "15m", "1h", "2h"], def: "15m" },
  { id: "1mo", label: "Monat", period: "1mo", res: ["5m", "15m", "1h", "2h", "1d"], def: "1h" },
  { id: "1y", label: "1 Jahr", period: "1y", res: ["1d", "1wk"], def: "1d" },
  { id: "3y", label: "3 Jahre", period: "3y", res: ["1d", "1wk"], def: "1d" },
  { id: "5y", label: "5 Jahre", period: "5y", res: ["1d", "1wk"], def: "1wk" },
  { id: "max", label: "Gesamt", period: "max", res: ["1d", "1wk"], def: "1wk" },
];
PERIOD_LABEL["3y"] = "3 Jahre";
PERIOD_LABEL.max = "Gesamt";

/** Auflösungen, die für diesen Zeitraum und Wert gehen. */
export function resolutionsFor(rangeId, meta) {
  const r = RANGES.find((x) => x.id === rangeId) || RANGES[3];
  const allowed = new Set(intervalsFor(meta).map((i) => i.id));
  const gettex = !!meta?.intraday_limit;
  return r.res.filter((iv) => allowed.has(iv) && (!gettex || !INTRADAY.has(iv) || ["1d", "5d"].includes(r.period)));
}

/** Zeitraum geht für diesen Wert? (Ohne Minutenkerzen gibt es „Tag“ und „Woche“ nicht.) */
export function rangeAvailable(rangeId, meta) {
  return resolutionsFor(rangeId, meta).length > 0;
}

/** Auflösung beim Wechsel des Zeitraums: die bisherige behalten, wenn sie passt, sonst die übliche. */
export function pickResolution(rangeId, current, meta) {
  const list = resolutionsFor(rangeId, meta);
  const r = RANGES.find((x) => x.id === rangeId);
  if (list.includes(current)) return current;
  return list.includes(r?.def) ? r.def : list[list.length - 1] || "1d";
}

/** Zeitraum zu einer gespeicherten Einstellung (period) finden; alte Zeiträume auf den nächsten neuen abbilden. */
export function rangeOfPeriod(period) {
  const map = { "3mo": "1y", "6mo": "1y", "2y": "3y", "10y": "max" };
  return RANGES.find((r) => r.period === period)?.id || map[period] || "1y";
}
