import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { dateTime, money, pct, signedMoney, tone } from "../fmt.js";
import { ACTION_UI, displayName } from "../texts.js";
import Modal from "./Modal.jsx";
import { ActionBadge, ErrorText, Loading } from "./ui.jsx";

const ORDER = { "Kaufen prüfen": 0, "Reduzieren prüfen": 1, "Halten / beobachten": 2 };

/** Morgenbericht als Dialog: oben das Wichtigste, darunter jeder Wert mit Begründung. */
export default function ReportModal({ id, onClose }) {
  const [rep, setRep] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(id ? `/reports/${id}` : "/reports/latest").then(setRep).catch((e) => setError(e.message));
  }, [id]);

  const entries = rep ? [...rep.entries].sort((a, b) => (ORDER[a.action] - ORDER[b.action])
    || (Math.abs(b.combined_score) - Math.abs(a.combined_score))) : [];
  const count = (act) => entries.filter((e) => e.action === act).length;
  const held = entries.filter((e) => e.holding?.shares);

  return (
    <Modal title={rep ? `Morgenbericht · ${rep.created}` : "Morgenbericht"} onClose={onClose} wide>
      <ErrorText error={error} />
      {!rep && !error && <Loading />}
      {rep && (
        <div className="report">
          <div className="report-sum">
            <div className="report-tile buy"><strong>{count("Kaufen prüfen")}</strong><span>{ACTION_UI["Kaufen prüfen"].label}</span></div>
            <div className="report-tile hold"><strong>{count("Halten / beobachten")}</strong><span>{ACTION_UI["Halten / beobachten"].label}</span></div>
            <div className="report-tile sell"><strong>{count("Reduzieren prüfen")}</strong><span>{ACTION_UI["Reduzieren prüfen"].label}</span></div>
            {held.length > 0 && <div className="report-tile"><strong>{held.length}</strong><span>im Depot</span></div>}
          </div>
          <p className="muted small">Strategie: {rep.profile}{rep.sent_at ? ` · verschickt ${dateTime(rep.sent_at)}` : ""} · Kurse vom Zeitpunkt des Berichts</p>
          <ul className="report-list">
            {entries.map((e) => (
              <li key={e.symbol} className={`report-item ${ACTION_UI[e.action]?.tone || ""}`}>
                <div className="report-head">
                  <Link to={`/chart/${encodeURIComponent(e.symbol)}`} onClick={onClose} className="report-name">{displayName(e)}</Link>
                  <ActionBadge action={e.action} held={!!e.holding?.shares} />
                  <span className="report-price">
                    {money(e.analysis.last_close, e.currency)} <span className={tone(e.analysis.change_pct_1d)}>{pct(e.analysis.change_pct_1d)}</span>
                  </span>
                </div>
                {e.holding?.shares > 0 && (
                  <p className={`small advice-inline ${e.holding.advice?.level || ""}`}>
                    💼 {e.holding.shares} Stück{e.holding.pl != null && <> · <span className={tone(e.holding.pl)}>{signedMoney(e.holding.pl, e.holding.currency)} ({pct(e.holding.pl_pct, 1)})</span></>} – {e.holding.advice?.text}
                  </p>
                )}
                <ul className="report-reasons small">
                  {e.reasons.slice(0, 3).map((r) => <li key={r}>{r}</li>)}
                </ul>
                {!e.holding?.shares && e.action !== "Kaufen prüfen" && e.entry?.summary && <p className="small muted">{e.entry.summary}</p>}
                {(e.stop || e.target) && (
                  <p className="small muted">{e.stop ? `Stopp ${money(e.stop, e.currency)}` : ""}{e.stop && e.target ? " · " : ""}{e.target ? `Ziel ${money(e.target, e.currency)}` : ""}</p>
                )}
                {e.news?.[0] && (
                  <p className="small report-news">📰 <a href={e.news[0].url} target="_blank" rel="noreferrer noopener">{e.news[0].headline}</a></p>
                )}
              </li>
            ))}
          </ul>
          {Object.keys(rep.errors || {}).length > 0 && (
            <p className="small error">Ohne Daten: {Object.keys(rep.errors).join(", ")}</p>
          )}
          <p className="muted small">{rep.disclaimer?.replace(/_/g, "")}</p>
        </div>
      )}
    </Modal>
  );
}
