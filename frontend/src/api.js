const TOKEN_KEY = "tradehelper_token";
const DEVICE_KEY = "tradehelper_device"; // „Gerät merken“: überspringt den 2FA-Code, das Passwort bleibt nötig

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => {
  localStorage.removeItem(TOKEN_KEY);
  // Zwischengespeicherte Seiten (cache.js) gehören zur Anmeldung und gehen mit
  try {
    Object.keys(localStorage).filter((k) => k.startsWith("th_cache:")).forEach((k) => localStorage.removeItem(k));
  } catch { /* egal */ }
};
export const getDevice = () => {
  try { return localStorage.getItem(DEVICE_KEY); } catch { return null; }
};
export const setDevice = (t) => {
  try { if (t) localStorage.setItem(DEVICE_KEY, t); else localStorage.removeItem(DEVICE_KEY); } catch { /* egal */ }
};

let onUnauthorized = () => {};
let onNeeds2fa = () => {};
export const setUnauthorizedHandler = (fn) => (onUnauthorized = fn);
export const setNeeds2faHandler = (fn) => (onNeeds2fa = fn);

const RESTARTING = new Set([502, 503, 504]); // nginx läuft, das Backend (noch) nicht – z. B. während eines Updates
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Bis zu ~30 s warten, bis der Server wieder antwortet (Neustart nach Update, kurzer Netzaussetzer). */
async function waitForServer(maxMs = 30000) {
  const until = Date.now() + maxMs;
  while (Date.now() < until) {
    await sleep(2000);
    try {
      const r = await fetch("/api/health", { cache: "no-store" });
      if (r.ok) return true;
    } catch { /* weiter warten */ }
  }
  return false;
}

function unreachable() {
  const offline = typeof navigator !== "undefined" && navigator.onLine === false;
  return new Error(offline
    ? "Du bist offline – bitte Verbindung prüfen."
    : "TradeHelper antwortet gerade nicht – vermutlich startet der Server neu (z. B. nach einem Update). Bitte in einer Minute noch einmal versuchen.");
}

async function send(method, path, headers, body) {
  return fetch(`/api${path}`, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
}

async function request(method, path, body) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  // Ist der Server kurz weg (Neustart, Netzaussetzer), warten wir auf ihn und versuchen es genau einmal erneut.
  // Doppelte Anfragen schaden nicht: Importe erkennen Doppeltes, alles andere ist ein Lesen oder Setzen.
  let res;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      res = await send(method, path, headers, body);
    } catch {
      res = null;
    }
    if (res && !RESTARTING.has(res.status)) break;
    if (attempt === 0 && (await waitForServer())) continue;
    if (!res) throw unreachable();
    break;
  }
  if (RESTARTING.has(res.status)) throw unreachable();

  if (res.status === 401 && !path.startsWith("/auth/")) {
    clearToken();
    onUnauthorized();
  }
  if (!res.ok) {
    let msg = `Fehler ${res.status}`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") msg = data.detail;
      else if (Array.isArray(data.detail)) msg = data.detail.map((d) => d.msg).join(", ");
    } catch {
      /* keine JSON-Antwort */
    }
    if (res.status === 403 && msg.startsWith("2FA_SETUP_REQUIRED")) {
      onNeeds2fa();
      msg = msg.replace(/^2FA_SETUP_REQUIRED:\s*/, "");
    }
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  get: (p) => request("GET", p),
  post: (p, b) => request("POST", p, b ?? {}),
  put: (p, b) => request("PUT", p, b),
  patch: (p, b) => request("PATCH", p, b),
  del: (p) => request("DELETE", p),
};

/** Datei als Base64 (für den Depot-Import). */
export function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1] || "");
    r.onerror = () => reject(new Error(`${file.name} nicht lesbar`));
    r.readAsDataURL(file);
  });
}
