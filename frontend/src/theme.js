/**
 * Hell/Dunkel und die Farben für Charts (lightweight-charts zeichnet auf eine Zeichenfläche und kennt kein CSS).
 * C.<name> liefert immer die Farbe des aktuellen Modus, alpha("up", 0.3) dieselbe Farbe mit Transparenz.
 */
const KEY = "tradehelper_theme"; // "light" | "dark" | "system"

const PALETTES = {
  light: {
    bg: "rgba(0, 0, 0, 0)", text: "#75736b", ink: "#1f1e1d", label: "#1f1e1d", onColor: "#ffffff",
    grid: "rgba(31, 30, 29, 0.06)", line: "rgba(31, 30, 29, 0.14)", neutral: "#a8a498",
    up: "#2f7a55", down: "#b5473a", amber: "#b07a20", accent: "#c6613f",
    buySig: "#2b6cb0", sellSig: "#9d3f98", orange: "#c2652a", blue: "#3f5fc6", purple: "#8a55c9",
    sma20: "#b07a20", sma50: "#3f5fc6", sma200: "#8a55c9", bb: "#a8a498", rsi: "#b07a20", macd: "#3f5fc6", signal: "#c2652a",
  },
  dark: {
    bg: "rgba(0, 0, 0, 0)", text: "#a5a39a", ink: "#f5f4ef", label: "#f5f4ef", onColor: "#1f1e1d",
    grid: "rgba(255, 255, 255, 0.05)", line: "rgba(255, 255, 255, 0.12)", neutral: "#6b6962",
    up: "#74c69d", down: "#ec8a7a", amber: "#e2b162", accent: "#d97757",
    buySig: "#7cb6f0", sellSig: "#db8bd6", orange: "#e89a6a", blue: "#8aa4ff", purple: "#c4a1ff",
    sma20: "#e2b162", sma50: "#8aa4ff", sma200: "#c4a1ff", bb: "#6b6962", rsi: "#e2b162", macd: "#8aa4ff", signal: "#e89a6a",
  },
};

export const FONT = '"Inter Variable", Inter, system-ui, -apple-system, sans-serif';

export function loadTheme() {
  try { return localStorage.getItem(KEY) || "system"; } catch { return "system"; }
}

export function resolvedTheme(pref = loadTheme()) {
  if (pref === "light" || pref === "dark") return pref;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function currentTheme() {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function applyTheme(pref = loadTheme()) {
  const t = resolvedTheme(pref);
  document.documentElement.dataset.theme = t;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", t === "dark" ? "#262624" : "#faf9f5");
  return t;
}

export function saveTheme(pref) {
  try { localStorage.setItem(KEY, pref); } catch { /* egal */ }
  const t = applyTheme(pref);
  window.dispatchEvent(new CustomEvent("th-theme", { detail: t }));
  return t;
}

/** Bei „System“ dem Betriebssystem folgen. */
export function watchSystemTheme() {
  const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
  if (!mq) return () => {};
  const fn = () => {
    if (loadTheme() === "system") {
      const t = applyTheme("system");
      window.dispatchEvent(new CustomEvent("th-theme", { detail: t }));
    }
  };
  mq.addEventListener?.("change", fn);
  return () => mq.removeEventListener?.("change", fn);
}

export const C = new Proxy({}, { get: (_, k) => PALETTES[currentTheme()][k] });

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`;
}

/** Farbe mit Transparenz, z. B. alpha("up", 0.25). */
export function alpha(name, a) {
  const c = PALETTES[currentTheme()][name] || name;
  if (c.startsWith("rgba")) return c;
  return `rgba(${hexToRgb(c)}, ${a})`;
}

/** Farbe aus einer Liste für Diagramme (Aufteilung, Linien). */
export const SERIES = ["#c6613f", "#3f5fc6", "#2f9e6e", "#b07a20", "#8a55c9", "#2b8fb0", "#c2457a", "#6b6962", "#7a9a2f", "#d0893a"];
