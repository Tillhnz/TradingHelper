import { useEffect } from "react";
import { useCachedGet } from "./cache.js";
import { api } from "./api.js";

/* Eine Reihenfolge für alle Listen von Werten (Startseite, Meine Werte, Portfolio) – vom Nutzer gewählt. */

export const SORTS = [
  { id: "custom", label: "Eigene", title: "Deine eigene Reihenfolge – unter „Meine Werte“ mit den Pfeilen festlegen" },
  { id: "name", label: "A–Z", title: "Alphabetisch nach Name" },
  { id: "day", label: "Heute", title: "Veränderung heute, größter Gewinn zuerst" },
  { id: "total", label: "Gesamt", title: "Veränderung seit Kauf (im Depot) bzw. seit Beobachtung, größter Gewinn zuerst" },
];
export const SORT_LABEL = { custom: "eigene Reihenfolge", name: "alphabetisch", day: "Veränderung heute", total: "Veränderung gesamt" };

const nameOf = (r) => (r.name || r.ticker || r.symbol || "").toString();

/** Zahl je Sortierart; fehlende Werte landen immer am Ende. */
function keyOf(r, sort, quotes) {
  if (sort === "day") {
    const q = quotes?.[r.symbol];
    const live = q && (!r.currency || q.currency === r.currency) ? q.change_pct : null;
    return live ?? r.change_pct ?? r.day_change_pct ?? null;
  }
  if (sort === "total") return r.holding?.pl_pct ?? r.pl_pct ?? r.since_pct ?? null;
  return null;
}

export function sortAssets(rows, sort = "custom", order = [], quotes = null) {
  if (!Array.isArray(rows)) return rows;
  const byName = (a, b) => nameOf(a).localeCompare(nameOf(b), "de", { sensitivity: "base" });
  const list = [...rows];
  if (sort === "name") return list.sort(byName);
  if (sort === "day" || sort === "total") {
    return list.sort((a, b) => {
      const ka = keyOf(a, sort, quotes);
      const kb = keyOf(b, sort, quotes);
      if (ka == null && kb == null) return byName(a, b);
      if (ka == null) return 1;
      if (kb == null) return -1;
      return kb - ka || byName(a, b);
    });
  }
  // eigene Reihenfolge; noch nicht eingeordnete Werte alphabetisch dahinter
  const pos = new Map(order.map((s, i) => [s, i]));
  return list.sort((a, b) => {
    const pa = pos.has(a.symbol) ? pos.get(a.symbol) : Infinity;
    const pb = pos.has(b.symbol) ? pos.get(b.symbol) : Infinity;
    return pa === pb ? byName(a, b) : pa - pb;
  });
}

export function parseOrder(value) {
  return String(value || "").split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
}

export function sortFrom(settingsData) {
  const fields = settingsData?.fields || {};
  return { sort: fields.asset_sort?.value || "custom", order: parseOrder(fields.asset_order?.value) };
}

const EVENT = "th:settings";

/** Andere Abfragen von /settings auf derselben Seite mitziehen, wenn eine Liste die Sortierung ändert. */
export function useSettingsSync(set) {
  useEffect(() => {
    const on = (e) => set(e.detail);
    window.addEventListener(EVENT, on);
    return () => window.removeEventListener(EVENT, on);
  }, [set]);
}

/** Gewählte Sortierung samt eigener Reihenfolge aus den Einstellungen, dazu Funktionen zum Ändern.
    Alle Listen auf der Seite ziehen sofort mit (Ereignis „th:settings“). */
export function useAssetSort() {
  const q = useCachedGet("/settings");
  useSettingsSync(q.set);
  const { sort, order } = sortFrom(q.data);
  async function save(values) {
    const r = await api.put("/settings", values);
    window.dispatchEvent(new CustomEvent(EVENT, { detail: r }));
    return r;
  }
  return {
    sort,
    order,
    ready: !!q.data,
    setSort: (s) => save({ asset_sort: s }),
    setOrder: (symbols) => save({ asset_order: symbols.join(","), asset_sort: "custom" }),
    apply: (rows, quotes) => sortAssets(rows, sort, order, quotes),
  };
}
