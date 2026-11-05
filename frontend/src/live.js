import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

/**
 * Aktuelle Kurse mehrerer Werte, alle `every` Millisekunden neu, solange die Seite sichtbar ist.
 * Liefert { [symbol]: { price, change_pct, time, bid, ask, bid_time, currency, delay_min } }.
 */
export function useLiveQuotes(symbols, { currency = null, every = 15000 } = {}) {
  const [quotes, setQuotes] = useState({});
  const key = [...new Set((symbols || []).filter(Boolean))].sort().join(",");
  const busy = useRef(false);

  useEffect(() => {
    if (!key) return undefined;
    let alive = true;
    const load = async () => {
      if (busy.current || document.visibilityState !== "visible") return;
      busy.current = true;
      try {
        const res = await api.get(`/quotes?symbols=${encodeURIComponent(key)}${currency ? `&currency=${currency}` : ""}`);
        if (alive) setQuotes(Object.fromEntries(res.filter((q) => q.price != null).map((q) => [q.symbol, q])));
      } catch { /* nächster Versuch */ } finally {
        busy.current = false;
      }
    };
    load();
    const id = setInterval(load, every);
    const onVisible = () => { if (document.visibilityState === "visible") load(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => { alive = false; clearInterval(id); document.removeEventListener("visibilitychange", onVisible); };
  }, [key, currency, every]);

  return quotes;
}

/** „vor 12 s“, „vor 3 Min.“, sonst Uhrzeit. */
export function since(unix) {
  if (!unix) return "";
  const s = Math.max(0, Math.round(Date.now() / 1000 - unix));
  if (s < 60) return `vor ${s} s`;
  if (s < 3600) return `vor ${Math.round(s / 60)} Min.`;
  const d = new Date(unix * 1000);
  const today = new Date().toDateString() === d.toDateString();
  return today ? `um ${d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })} Uhr`
    : d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}
