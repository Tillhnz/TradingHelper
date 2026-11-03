const nf = (d) => new Intl.NumberFormat("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });

export function num(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const abs = Math.abs(v);
  const d = digits ?? (abs >= 1000 ? 0 : abs >= 1 ? 2 : 4);
  return nf(d).format(v);
}

export function price(v) {
  if (v === null || v === undefined) return "–";
  return num(v, Math.abs(v) >= 1 || v === 0 ? 2 : 4);
}

const SYMBOL = { EUR: "€", USD: "$", GBP: "£", CHF: "CHF", JPY: "¥" };

/** Preis mit Währung, z. B. „187,40 €“, „187,40 $“, „1.234 GBp“. Ohne Währung (Index) nur die Zahl. */
export function money(v, ccy) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  const n = price(v);
  if (!ccy) return n;
  return `${n} ${SYMBOL[ccy] || ccy}`;
}

export const CURRENCY_LABEL = {
  native: "Handelswährung", EUR: "Euro (€)", USD: "US-Dollar ($)", CHF: "Franken (CHF)", GBP: "Pfund (£)",
};

export function pct(v, digits = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  return `${v > 0 ? "+" : ""}${nf(digits).format(v)} %`;
}

export function signed(v, digits = 2) {
  if (v === null || v === undefined) return "–";
  return `${v > 0 ? "+" : ""}${nf(digits).format(v)}`;
}

export function dateTime(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("de-DE", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function tone(v) {
  if (v === null || v === undefined) return "";
  return v > 0 ? "pos" : v < 0 ? "neg" : "";
}

export const ACTION_TONE = {
  "Kaufen prüfen": "buy",
  "Halten / beobachten": "hold",
  "Reduzieren prüfen": "sell",
};
