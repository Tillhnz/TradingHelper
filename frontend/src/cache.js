import { useCallback, useEffect, useRef, useState } from "react";
import { api, getToken } from "./api.js";

/**
 * Zuletzt geladener Stand je Abfrage im Browser – damit Seiten sofort etwas zeigen
 * und die frischen Daten im Hintergrund nachladen („stale while revalidate“).
 * Pro Anmeldung getrennt; beim Abmelden wird alles gelöscht.
 */
const PREFIX = "th_cache:";

function scope() {
  const t = getToken() || "";
  return t.slice(-16);
}

export function readCache(path) {
  try {
    const raw = localStorage.getItem(`${PREFIX}${scope()}:${path}`);
    if (!raw) return null;
    const v = JSON.parse(raw);
    return v && "data" in v ? v : null;
  } catch {
    return null;
  }
}

export function writeCache(path, data) {
  const key = `${PREFIX}${scope()}:${path}`;
  const value = JSON.stringify({ at: Date.now(), data });
  try {
    localStorage.setItem(key, value);
  } catch {
    // Speicher voll: alte Einträge wegräumen und einmal neu versuchen
    clearCache();
    try { localStorage.setItem(key, value); } catch { /* dann eben ohne */ }
  }
}

export function clearCache() {
  try {
    Object.keys(localStorage).filter((k) => k.startsWith(PREFIX)).forEach((k) => localStorage.removeItem(k));
  } catch { /* egal */ }
}

/**
 * Daten einer GET-Abfrage: sofort der gespeicherte Stand, frische Daten kommen im Hintergrund.
 * Liefert { data, at (ms, Stand der gezeigten Daten), refreshing, error, reload }.
 * `error` ist nur gesetzt, wenn gar nichts gezeigt werden kann; sonst `refreshError`.
 */
export function useCachedGet(path, { enabled = true } = {}) {
  const [state, setState] = useState(() => {
    const c = enabled && path ? readCache(path) : null;
    return { data: c ? c.data : null, at: c ? c.at : null, refreshing: !!(enabled && path), error: "", refreshError: "" };
  });
  const seq = useRef(0);

  const reload = useCallback(async () => {
    if (!enabled || !path) return;
    const n = ++seq.current;
    setState((s) => ({ ...s, refreshing: true, refreshError: "" }));
    try {
      const data = await api.get(path);
      if (n !== seq.current) return;
      writeCache(path, data);
      setState({ data, at: Date.now(), refreshing: false, error: "", refreshError: "" });
    } catch (e) {
      if (n !== seq.current) return;
      setState((s) => (s.data != null
        ? { ...s, refreshing: false, refreshError: e.message }
        : { ...s, refreshing: false, error: e.message }));
    }
  }, [path, enabled]);

  useEffect(() => {
    if (!enabled || !path) return;
    const c = readCache(path);
    if (c) setState((s) => (s.data === c.data ? s : { ...s, data: c.data, at: c.at }));
    reload();
  }, [path, enabled, reload]);

  const set = useCallback((fn) => setState((s) => {
    const data = typeof fn === "function" ? fn(s.data) : fn;
    if (path) writeCache(path, data);
    return { ...s, data };
  }), [path]);

  return { ...state, reload, set };
}

/** „Stand 18:42“ bzw. „Stand 11.11. 18:42“ */
export function standLabel(ms) {
  if (!ms) return "";
  const d = new Date(ms);
  const today = new Date().toDateString() === d.toDateString();
  return `Stand ${today ? "" : `${d.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })} `}${d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}`;
}
