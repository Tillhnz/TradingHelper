import { money } from "../fmt.js";
import Icon from "./Icon.jsx";

const pc = (v) => `${Math.round(v * 100)} %`;
const span = (days) => (days <= 5 ? "nächste Woche" : `nächste ${Math.round(days / 5)} Wochen`);

/** Kleines Kürzel für Listen: nur, wenn eine Richtung klar wahrscheinlicher ist. */
export function BreakoutChip({ bo }) {
  if (!bo || bo.tilt === "neutral") return null;
  const up = bo.tilt === "up";
  return (
    <span className={`bo-chip ${up ? "up" : "down"}`} title={`${up ? "Ausbruch-Chance erhöht" : "Rutsch-Risiko erhöht"}: ${pc(up ? bo.up : bo.down)} (üblich ${pc(up ? bo.base_up : bo.base_down)}), ${span(bo.days)}`}>
      <Icon name={up ? "up" : "down"} />{pc(up ? bo.up : bo.down)}
    </span>
  );
}

/** Wie die Nachrichtenlage die Wahrscheinlichkeiten verschoben hat. */
function NewsEffect({ n, bo }) {
  const mood = n.sentiment > 0.15 ? "positiv" : n.sentiment < -0.15 ? "negativ" : "neutral";
  const du = Math.round((bo.up - n.up_before) * 100);
  const dd = Math.round((bo.down - n.down_before) * 100);
  const sig = (v) => (v > 0 ? `+${v}` : `${v}`);
  return (
    <p className={`bo-news ${mood}`}>
      <Icon name="news" />
      <span>
        Nachrichtenlage <strong>{mood}</strong>{n.count ? ` (${n.count} Meldungen)` : ""}
        {du || dd ? <> · eingerechnet: Ausbruch {sig(du)} Pkt., Rutsch {sig(dd)} Pkt.</> : " · kaum Einfluss"}
      </span>
    </p>
  );
}

/**
 * Ausbruch- und Rutsch-Wahrscheinlichkeit aus der eigenen Kursgeschichte des Werts: Wie oft ging es in ähnlicher
 * Lage über das Hoch bzw. unter das Tief der letzten Wochen?
 */
export default function BreakoutMeter({ bo, currency }) {
  if (!bo) return null;
  const rows = [
    { key: "up", icon: "up", label: "Ausbruch nach oben", level: `über ${money(bo.level_up, currency)}`, p: bo.up, base: bo.base_up },
    { key: "down", icon: "down", label: "Rutsch nach unten", level: `unter ${money(bo.level_down, currency)}`, p: bo.down, base: bo.base_down },
  ];
  const verdict = bo.tilt === "up" ? "Die Chancen auf einen Ausbruch nach oben stehen besser als sonst."
    : bo.tilt === "down" ? "Das Risiko eines Rutsches nach unten ist erhöht – Stopp im Blick behalten."
      : "Keine Richtung sticht heraus – eher eine Seitwärtsphase.";
  return (
    <section className={`panel breakout tilt-${bo.tilt}`} aria-labelledby="bo-h">
      <div className="panel-head">
        <h2 id="bo-h"><Icon name="zap" className="h-icon" /> Ausbruch-Chance</h2>
        <span className="muted small"><Icon name="clock" /> {span(bo.days)}</span>
      </div>
      <p className="bo-verdict">{verdict}</p>
      <div className="bo-rows">
        {rows.map((r) => (
          <div key={r.key} className={`bo-row ${r.key}`}>
            <div className="bo-top">
              <span className="bo-label"><Icon name={r.icon} /> {r.label}</span>
              <strong className="bo-pct">{pc(r.p)}</strong>
            </div>
            <div className="bo-track" role="img" aria-label={`${r.label}: ${pc(r.p)}, üblich ${pc(r.base)}`}>
              <span className="bo-fill" style={{ width: `${Math.max(2, r.p * 100)}%` }} />
              <span className="bo-base" style={{ left: `${r.base * 100}%` }} title={`üblich ${pc(r.base)}`} />
            </div>
            <span className="muted small">Schlusskurs {r.level} · üblich {pc(r.base)}</span>
          </div>
        ))}
      </div>
      {bo.news && <NewsEffect n={bo.news} bo={bo} />}
      <p className="muted small bo-foot">
        <Icon name="info" /> Aus {bo.samples} Handelstagen dieses Werts: wie es in den {bo.neighbors} ähnlichsten Lagen weiterging.
        Keine Garantie – eine Einschätzung wie die übrigen.
      </p>
    </section>
  );
}
