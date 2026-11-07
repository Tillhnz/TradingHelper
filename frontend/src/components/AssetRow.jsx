import { Link } from "react-router-dom";
import { money, num, pct, signedMoney, tone } from "../fmt.js";
import { ACTION_UI } from "../texts.js";

const HELD_SHORT = { "Kaufen prüfen": "Nachkauf?", "Halten / beobachten": "Halten", "Reduzieren prüfen": "Verkauf prüfen" };
// Winzige Beträge (Rundung) als 0 zeigen statt „−0,0000 €“
const clean = (v, digits = 2) => (v == null ? v : Math.abs(v) < 0.5 * 10 ** -digits ? 0 : Math.round(v * 10 ** digits) / 10 ** digits);

/**
 * Eine kompakte Zeile pro Wert – überall gleich: links Name und das Wichtigste in einer Zeile, rechts zwei Zahlen,
 * darunter höchstens ein Hinweis, wenn etwas zu tun ist. Die ganze Zeile führt zur Seite des Werts.
 *
 * top/bottom: die zwei Zahlen rechts ({ text, tone })
 * meta: kurze Zusatzinfo unter dem Namen (Kürzel, Stückzahl …)
 * hint: { level, text } – nur wenn es etwas zu tun oder zu wissen gibt
 */
export default function AssetRow({ symbol, name, meta, top, bottom, action, held = false, hint, error }) {
  const ui = ACTION_UI[action];
  const label = held ? HELD_SHORT[action] : ui?.short;
  return (
    <li className={`asset-row ${ui?.tone || ""} ${held ? "held" : ""}`}>
      <Link to={`/chart/${encodeURIComponent(symbol)}`} className="asset-link">
        <span className={`asset-dot ${ui?.tone || ""}`} title={label || ""} aria-hidden="true" />
        <span className="asset-main">
          <span className="asset-name">{name}</span>
          <span className="asset-meta">
            {label && <span className={`asset-tag ${ui?.tone || ""}`}>{label}</span>}
            {meta}
          </span>
        </span>
        <span className="asset-nums">
          {error ? <span className="error small">keine Kurse</span> : (
            <>
              <strong className={top?.tone || ""}>{top?.text}</strong>
              <span className={`small ${bottom?.tone || ""}`}>{bottom?.text}</span>
            </>
          )}
        </span>
        <span className="asset-go" aria-hidden="true">›</span>
      </Link>
      {hint && <p className={`asset-hint ${hint.level || ""}`}>{hint.text}</p>}
    </li>
  );
}

/** Zahlen für einen gehaltenen Wert: Wert rechts oben, Gewinn/Verlust darunter. */
export function heldNums(h, fallbackCcy) {
  const c = h.currency || fallbackCcy;
  return {
    top: { text: h.value != null ? money(h.value, c) : `${num(h.shares, h.shares % 1 ? 3 : 0)} Stück` },
    bottom: h.pl != null ? { text: `${signedMoney(clean(h.pl), c)} · ${pct(clean(h.pl_pct, 1), 1)}`, tone: tone(clean(h.pl)) } : null,
  };
}

/** Zahlen für einen beobachteten Wert: Kurs und Tagesänderung. */
export function priceNums(price, change, currency) {
  return {
    top: { text: money(price, currency) },
    bottom: change != null ? { text: `${pct(clean(change))} heute`, tone: tone(clean(change)) } : null,
  };
}

/** Nur Hinweise zeigen, bei denen etwas zu tun ist – „Halten, kein Handlungsbedarf“ bleibt weg. */
export function actionHint(advice) {
  if (!advice?.text) return null;
  if (/kein Handlungsbedarf/i.test(advice.text)) return null;
  const text = advice.text.replace(/^Halten – /, "").replace(/^Nachkauf möglich(; )?/, "");
  return text ? { level: advice.level, text: text.charAt(0).toUpperCase() + text.slice(1) } : null;
}
