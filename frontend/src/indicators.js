// Kennlinien für den Chart-Arbeitsplatz, im Browser gerechnet (Perioden frei wählbar).

export function sma(values, n) {
  const out = new Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i += 1) {
    sum += values[i];
    if (i >= n) sum -= values[i - n];
    if (i >= n - 1) out[i] = sum / n;
  }
  return out;
}

export function ema(values, n) {
  const out = new Array(values.length).fill(null);
  const k = 2 / (n + 1);
  let prev = null;
  for (let i = 0; i < values.length; i += 1) {
    if (i < n - 1) continue;
    if (prev === null) {
      prev = values.slice(0, n).reduce((a, b) => a + b, 0) / n; // Start mit dem einfachen Durchschnitt
    } else {
      prev = values[i] * k + prev * (1 - k);
    }
    out[i] = prev;
  }
  return out;
}

export function bollinger(values, n = 20, mult = 2) {
  const mid = sma(values, n);
  const upper = [], lower = [];
  for (let i = 0; i < values.length; i += 1) {
    if (mid[i] === null) { upper.push(null); lower.push(null); continue; }
    let v = 0;
    for (let j = i - n + 1; j <= i; j += 1) v += (values[j] - mid[i]) ** 2;
    const sd = Math.sqrt(v / n);
    upper.push(mid[i] + mult * sd);
    lower.push(mid[i] - mult * sd);
  }
  return { mid, upper, lower };
}

/** RSI nach Wilder (wie im Backend). */
export function rsi(values, n = 14) {
  const out = new Array(values.length).fill(null);
  if (values.length <= n) return out;
  let gain = 0, loss = 0;
  for (let i = 1; i <= n; i += 1) {
    const d = values[i] - values[i - 1];
    gain += Math.max(d, 0);
    loss += Math.max(-d, 0);
  }
  gain /= n;
  loss /= n;
  out[n] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
  for (let i = n + 1; i < values.length; i += 1) {
    const d = values[i] - values[i - 1];
    gain = (gain * (n - 1) + Math.max(d, 0)) / n;
    loss = (loss * (n - 1) + Math.max(-d, 0)) / n;
    out[i] = loss === 0 ? 100 : 100 - 100 / (1 + gain / loss);
  }
  return out;
}

export function macd(values, fast = 12, slow = 26, signal = 9) {
  const f = ema(values, fast), s = ema(values, slow);
  const line = values.map((_, i) => (f[i] !== null && s[i] !== null ? f[i] - s[i] : null));
  const start = line.findIndex((v) => v !== null);
  const sig = new Array(values.length).fill(null);
  if (start >= 0) {
    const e = ema(line.slice(start), signal);
    e.forEach((v, i) => { sig[start + i] = v; });
  }
  const hist = line.map((v, i) => (v !== null && sig[i] !== null ? v - sig[i] : null));
  return { line, signal: sig, hist };
}

export const INDICATORS = {
  sma: { label: "Gleitender Durchschnitt (SMA)", short: "SMA", params: { period: 50 }, pane: "main",
    explain: "Mittlerer Kurs der letzten n Tage. Zeigt den Trend; Kurs darüber = eher aufwärts." },
  ema: { label: "Exponentieller Durchschnitt (EMA)", short: "EMA", params: { period: 21 }, pane: "main",
    explain: "Wie SMA, gewichtet aber die letzten Tage stärker und reagiert schneller." },
  bb: { label: "Bollinger-Bänder", short: "Bollinger", params: { period: 20, mult: 2 }, pane: "main",
    explain: "Band um den Durchschnitt mit der üblichen Schwankung. Außerhalb = ungewöhnlich weit gelaufen." },
  volume: { label: "Volumen", short: "Volumen", params: {}, pane: "main",
    explain: "Wie viel gehandelt wurde. Bewegungen mit hohem Volumen sind aussagekräftiger." },
  rsi: { label: "RSI (Relative Stärke)", short: "RSI", params: { period: 14 }, pane: "sub",
    explain: "0–100. Über 70 heißgelaufen, unter 30 stark gefallen." },
  macd: { label: "MACD", short: "MACD", params: { fast: 12, slow: 26, signal: 9 }, pane: "sub",
    explain: "Trendfolge: Kreuzt die MACD-Linie ihre Signallinie nach oben, dreht das Momentum nach oben." },
};

export const PARAM_LABEL = { period: "Tage", mult: "Breite", fast: "schnell", slow: "langsam", signal: "Signal" };

export function indicatorTitle(ind) {
  const def = INDICATORS[ind.kind];
  const p = ind.params || {};
  if (ind.kind === "sma" || ind.kind === "ema" || ind.kind === "rsi") return `${def.short} ${p.period}`;
  if (ind.kind === "bb") return `${def.short} ${p.period}/${p.mult}`;
  if (ind.kind === "macd") return `${def.short} ${p.fast}/${p.slow}/${p.signal}`;
  return def.short;
}
