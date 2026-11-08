// Positions-Box wie das „Long-Position“-Werkzeug in TradingView: ab dem Kaufzeitpunkt ein grüner Bereich bis zum
// Ziel und ein roter bis zum Stopp, dazu der aktuelle Gewinn/Verlust als kräftigere Fläche zwischen Kaufkurs und
// aktuellem Kurs. Umgesetzt als „Series Primitive“ von lightweight-charts (eigenes Zeichnen auf der Zeichenfläche).

const C = {
  win: "rgba(111, 211, 195, 0.16)", winEdge: "rgba(111, 211, 195, 0.55)", winStrong: "rgba(111, 211, 195, 0.38)",
  loss: "rgba(255, 107, 107, 0.16)", lossEdge: "rgba(255, 107, 107, 0.55)", lossStrong: "rgba(255, 107, 107, 0.38)",
  entry: "#f2b84b", text: "#0e1620", label: "#e6edf3",
};

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

function pill(ctx, text, x, y, bg, fg, align = "right") {
  ctx.font = "600 11px system-ui, -apple-system, Segoe UI, sans-serif";
  const w = ctx.measureText(text).width + 12;
  const maxX = ctx.canvas.width / (window.devicePixelRatio || 1);
  // immer ganz sichtbar halten (z. B. Kauf von heute ganz rechts im Chart)
  const left = Math.max(2, Math.min(align === "right" ? x - w : x, maxX - w - 2));
  ctx.fillStyle = bg;
  roundRect(ctx, left, y - 9, w, 18, 5);
  ctx.fill();
  ctx.fillStyle = fg;
  ctx.textBaseline = "middle";
  ctx.fillText(text, left + 6, y + 0.5);
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
      const { entry, stop, target: tgt, price, qty, fees = 0, fmt, fmtPct, end, label } = this.o;
      const pl = (v) => qty * (v - entry) - fees;
      const pc = (v) => (v / entry - 1) * 100;
      const right = Math.min(g.xEnd, mediaSize.width) - 6;
      if (!end && g.yTarget !== null && tgt) {
        pill(ctx, `Ziel ${fmt(tgt)} · ${fmtPct(pc(tgt))} · ${fmt(pl(tgt), true)}`, right, g.yTarget + (g.yTarget < g.yEntry ? 12 : -12), "rgba(111, 211, 195, 0.9)", C.text);
      }
      if (!end && g.yStop !== null && stop) {
        pill(ctx, `Stopp ${fmt(stop)} · ${fmtPct(pc(stop))} · ${fmt(pl(stop), true)}`, right, g.yStop + (g.yStop > g.yEntry ? -12 : 12), "rgba(255, 107, 107, 0.9)", C.text);
      }
      const x = Math.max(4, g.x0 + 4);
      pill(ctx, label, x, g.yEntry + (price != null && price < entry ? -12 : 12), "rgba(242, 184, 75, 0.92)", C.text, "left");
      if (price != null && g.yPrice !== null) {
        const v = pl(price);
        const txt = `${end ? "Ergebnis " : ""}${fmt(v, true)} (${fmtPct(pc(price))})`;
        const xr = Math.min(g.xNow + 6 + 120, mediaSize.width - 70);
        pill(ctx, txt, Math.max(xr, x + 140), g.yPrice, v >= 0 ? "#6fd3c3" : "#ff6b6b", C.text);
      }
    });
  }
}
