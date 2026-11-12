// Positions-Box wie das „Long-Position“-Werkzeug in TradingView: ab dem Kaufzeitpunkt ein grüner Bereich bis zum
// Ziel und ein roter bis zum Stopp, dazu der aktuelle Gewinn/Verlust als kräftigere Fläche zwischen Kaufkurs und
// aktuellem Kurs. Umgesetzt als „Series Primitive“ von lightweight-charts (eigenes Zeichnen auf der Zeichenfläche).

// Flächen bewusst zart, damit die Kerzen darunter lesbar bleiben
const C = {
  win: "rgba(111, 211, 195, 0.06)", winEdge: "rgba(111, 211, 195, 0.5)", winStrong: "rgba(111, 211, 195, 0.13)",
  loss: "rgba(255, 107, 107, 0.06)", lossEdge: "rgba(255, 107, 107, 0.5)", lossStrong: "rgba(255, 107, 107, 0.13)",
  entry: "#f2b84b", text: "#0e1620", label: "#e6edf3",
};
const COMPACT = 640; // schmaler als das: kurze Beschriftungen

/** Index der letzten Kerze, die zum Zeitpunkt t schon begonnen hatte (Kerzen sind aufsteigend sortiert). */
export function barIndex(times, t) {
  let lo = 0, hi = times.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

/** Zeitpunkt des Kaufs in Sekunden. Ohne Uhrzeit: Mittag des Kauftags (liegt sicher in der Tageskerze). */
export function buyTimestamp(p) {
  const [y, m, d] = String(p.buy_date).split("-").map(Number);
  const [hh, mm] = p.buy_time ? p.buy_time.split(":").map(Number) : [12, 0];
  return Math.floor(new Date(y, m - 1, d, hh, mm).getTime() / 1000);
}

export function sellTimestamp(p) {
  if (!p.sell_date) return null;
  const [y, m, d] = String(p.sell_date).split("-").map(Number);
  const [hh, mm] = p.sell_time ? p.sell_time.split(":").map(Number) : [12, 0];
  return Math.floor(new Date(y, m - 1, d, hh, mm).getTime() / 1000);
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function pill(ctx, text, x, y, bg, fg, align = "right", maxX = Infinity, small = false) {
  ctx.font = `600 ${small ? 10 : 11}px system-ui, -apple-system, Segoe UI, sans-serif`;
  const h = small ? 15 : 17;
  const w = ctx.measureText(text).width + (small ? 9 : 12);
  // immer ganz sichtbar halten (z. B. Kauf von heute ganz rechts im Chart)
  const left = Math.max(2, Math.min(align === "right" ? x - w : x, maxX - w - 2));
  ctx.globalAlpha = 0.82;
  ctx.fillStyle = bg;
  roundRect(ctx, left, y - h / 2, w, h, 4);
  ctx.fill();
  ctx.globalAlpha = 1;
  ctx.fillStyle = fg;
  ctx.textBaseline = "middle";
  ctx.fillText(text, left + (small ? 4.5 : 6), y + 0.5);
}

/** Beschriftungen, die sich überlappen würden, auseinanderschieben (Abstand mind. eine Pillenhöhe). */
function spread(items, gap) {
  const sorted = [...items].sort((a, b) => a.y - b.y);
  for (let i = 1; i < sorted.length; i += 1) {
    if (sorted[i].y - sorted[i - 1].y < gap) sorted[i].y = sorted[i - 1].y + gap;
  }
  return items;
}

export class PositionBox {
  /**
   * o: { times: [Kerzenzeiten], start, end (null = offen), entry, stop, target, price, qty, fees, fmt(value), fmtPct(v),
   *      label }
   */
  constructor(o) {
    this.o = o;
    this._views = [
      { zOrder: () => "bottom", renderer: () => ({ draw: (t) => this.drawBoxes(t) }) },
      { zOrder: () => "top", renderer: () => ({ draw: (t) => this.drawLabels(t) }) },
    ];
  }

  attached({ chart, series, requestUpdate }) {
    this.chart = chart;
    this.series = series;
    this.requestUpdate = requestUpdate;
  }

  detached() {
    this.chart = null;
  }

  update(patch) {
    this.o = { ...this.o, ...patch };
    this.requestUpdate?.();
  }

  updateAllViews() {}

  paneViews() {
    return this._views;
  }

  /** Stopp und Ziel offener Positionen gehören in die automatische Skalierung (wie bei TradingView). */
  autoscaleInfo() {
    const { entry, stop, target, end } = this.o;
    if (end) return null;
    const vals = [entry, stop, target].filter((v) => v != null);
    return { priceRange: { minValue: Math.min(...vals), maxValue: Math.max(...vals) } };
  }

  geometry(width) {
    const { times, start, end, entry, stop, target, price } = this.o;
    if (!this.chart || !this.series || !times?.length) return null;
    const ts = this.chart.timeScale();
    const i0 = Math.max(0, barIndex(times, start));
    const i1 = end ? Math.max(i0, barIndex(times, end)) : times.length - 1;
    const half = (ts.options().barSpacing || 6) / 2;
    const x0 = ts.logicalToCoordinate(i0);
    const xNow = ts.logicalToCoordinate(i1);
    if (x0 === null || xNow === null) return null;
    const y = (v) => (v == null ? null : this.series.priceToCoordinate(v));
    return {
      x0: x0 - half, xNow: xNow + half, xEnd: end ? xNow + half : width,
      yEntry: y(entry), yStop: y(stop), yTarget: y(target), yPrice: y(price),
    };
  }

  drawBoxes(target) {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const g = this.geometry(mediaSize.width);
      if (!g || g.yEntry === null) return;
      const { end, price, entry } = this.o;
      const w = g.xEnd - g.x0;
      if (!end) {
        if (g.yTarget !== null) {
          ctx.fillStyle = C.win;
          ctx.fillRect(g.x0, Math.min(g.yTarget, g.yEntry), w, Math.abs(g.yEntry - g.yTarget));
          ctx.strokeStyle = C.winEdge;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(g.x0, g.yTarget);
          ctx.lineTo(g.xEnd, g.yTarget);
          ctx.stroke();
        }
        if (g.yStop !== null) {
          ctx.fillStyle = C.loss;
          ctx.fillRect(g.x0, Math.min(g.yStop, g.yEntry), w, Math.abs(g.yEntry - g.yStop));
          ctx.strokeStyle = C.lossEdge;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(g.x0, g.yStop);
          ctx.lineTo(g.xEnd, g.yStop);
          ctx.stroke();
        }
      }
      // aktueller (bzw. beim Verkauf erzielter) Gewinn/Verlust
      if (g.yPrice !== null && price != null) {
        ctx.fillStyle = price >= entry ? C.winStrong : C.lossStrong;
        ctx.fillRect(g.x0, Math.min(g.yPrice, g.yEntry), g.xNow - g.x0, Math.abs(g.yEntry - g.yPrice));
      }
      ctx.strokeStyle = C.entry;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(g.x0, g.yEntry);
      ctx.lineTo(g.xEnd, g.yEntry);
      ctx.stroke();
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(g.x0, Math.min(g.yEntry, g.yTarget ?? g.yEntry, g.yPrice ?? g.yEntry));
      ctx.lineTo(g.x0, Math.max(g.yEntry, g.yStop ?? g.yEntry, g.yPrice ?? g.yEntry));
      ctx.stroke();
    });
  }

  drawLabels(target) {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const g = this.geometry(mediaSize.width);
      if (!g || g.yEntry === null) return;
      const { entry, stop, target: tgt, price, qty, fees = 0, fmt, fmtPct, end, label, short } = this.o;
      const pl = (v) => qty * (v - entry) - fees;
      const pc = (v) => (v / entry - 1) * 100;
      const W = mediaSize.width;
      const small = W < COMPACT;
      const right = Math.min(g.xEnd, W) - 4;
      const gap = small ? 17 : 19;
      // Gewinn/Verlust steht mit am Kaufkurs – keine eigene Marke auf der Kurslinie, die den Verlauf verdeckt
      const now = price != null ? `${end ? "Ergebnis " : ""}${fmt(pl(price), true)} (${fmtPct(pc(price))})` : "";
      const items = [];
      if (!end && g.yTarget !== null && tgt) {
        items.push({ y: g.yTarget + (g.yTarget < g.yEntry ? 11 : -11), x: right, align: "right", bg: "rgba(111, 211, 195, 0.95)",
          text: small ? `Ziel ${fmtPct(pc(tgt))}` : `Ziel ${fmt(tgt)} · ${fmtPct(pc(tgt))} · ${fmt(pl(tgt), true)}` });
      }
      if (!end && g.yStop !== null && stop) {
        items.push({ y: g.yStop + (g.yStop > g.yEntry ? -11 : 11), x: right, align: "right", bg: "rgba(255, 107, 107, 0.95)",
          text: small ? `Stopp ${fmtPct(pc(stop))}` : `Stopp ${fmt(stop)} · ${fmtPct(pc(stop))} · ${fmt(pl(stop), true)}` });
      }
      const up = price != null && price >= entry;
      // Alle Beschriftungen rechts übereinander – im freien Bereich hinter der letzten Kerze statt mitten im Verlauf
      items.push({ y: g.yEntry + (up ? 11 : -11), x: right, align: "right", bg: "rgba(242, 184, 75, 0.95)",
        text: small ? `${short || label}${now ? ` · ${fmtPct(pc(price))}` : ""}` : `${label}${now ? ` · ${now}` : ""}` });
      spread(items, gap).forEach((i) => pill(ctx, i.text, i.x, i.y, i.bg, C.text, i.align, W, small));
    });
  }
}
