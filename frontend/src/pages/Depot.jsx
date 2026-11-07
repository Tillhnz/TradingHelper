import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import AssetRow, { actionHint, heldNums } from "../components/AssetRow.jsx";
import BuyDialog from "../components/BuyDialog.jsx";
import DepotTabs from "../components/DepotTabs.jsx";
import PnlChart from "../components/PnlChart.jsx";
import { Empty, ErrorText, Loading } from "../components/ui.jsx";
import { money, num, pct, signedMoney, tone } from "../fmt.js";
import { useLiveQuotes } from "../live.js";
import { displayName } from "../texts.js";

export default function Depot() {
  const [data, setData] = useState(null);
  const [hist, setHist] = useState(null);
  const [error, setError] = useState("");
  const [buying, setBuying] = useState(false);
  const [showChart, setShowChart] = useState(false);
  const [showClosed, setShowClosed] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api.get("/positions"));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (showChart && !hist) api.get("/positions/history").then(setHist).catch(() => {});
  }, [showChart, hist]);

  const groups = data?.groups || [];
  const open = groups.filter((g) => g.shares > 0);
  const closed = groups.filter((g) => !g.shares && g.closed_lots);
  const t = data?.totals;
  const quotes = useLiveQuotes(open.map((g) => g.symbol));

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Depot</h1>
          <p className="muted">Deine Käufe mit Gewinn und Verlust. Antippen öffnet alle Details, Stopp, Ziel und Verkauf.</p>
        </div>
        <button className="btn primary" onClick={() => setBuying(true)}>Kauf erfassen</button>
      </div>
      <DepotTabs />
      <ErrorText error={error} />
      {!data && !error && <Loading />}

      {data && !data.items.length && (
        <Empty title="Noch keine Käufe erfasst">
          <p className="muted">Öffne einen Wert und tippe auf „Kauf“ – Kurs und Uhrzeit werden übernommen. Danach siehst du hier deinen Gewinn oder Verlust.</p>
          <button className="btn primary" onClick={() => setBuying(true)}>Ersten Kauf erfassen</button>
        </Empty>
      )}

      {data && data.items.length > 0 && (
        <>
          <div className="hero-total">
            <span className="label">Depotwert</span>
            <span className="big">{money(t.value, t.currency)}</span>
            <strong className={tone(t.pl)}>{signedMoney(t.pl, t.currency)} · {pct(t.pl_pct, 1)}</strong>
            <span className="sub">
              eingesetzt {money(t.invested, t.currency)}
              {t.realized ? <> · bereits realisiert <span className={tone(t.realized)}>{signedMoney(t.realized, t.currency)}</span></> : null}
              {" · "}<button className="toggle-link" onClick={() => setShowChart((v) => !v)}>{showChart ? "Verlauf ausblenden" : "Verlauf zeigen"}</button>
            </span>
          </div>

          {showChart && (
            <section className="panel chart-panel">
              {!hist ? <Loading /> : hist.points?.length > 1 ? <PnlChart points={hist.points} /> : <p className="muted small">Noch zu wenig Verlauf.</p>}
            </section>
          )}

          {open.length > 0 && (
            <>
              <div className="list-head"><h2>Im Depot</h2><span className="muted small">{open.length} {open.length === 1 ? "Wert" : "Werte"}</span></div>
              <ul className="asset-list">
                {open.map((g) => {
                  const q = quotes[g.symbol];
                  const liveOk = q && q.currency === g.currency && g.invested;
                  const value = liveOk ? g.shares * q.price : g.value;
                  const nums = heldNums(liveOk ? { ...g, value, pl: value - g.invested, pl_pct: (value / g.invested - 1) * 100 } : g, g.currency);
                  const change = q && q.currency === g.currency && q.change_pct != null ? q.change_pct : g.day_change_pct;
                  return (
                    <AssetRow key={g.symbol} symbol={g.symbol} name={displayName(g)} action={g.action} held error={g.error}
                      meta={<>{num(g.shares, g.shares % 1 ? 3 : 0)} Stück{g.lots > 1 ? ` · ${g.lots} Käufe` : ""}{change != null && <> · <span className={tone(change)}>{pct(change)} heute</span></>}</>}
                      top={nums.top} bottom={nums.bottom} hint={actionHint(g.advice)} />
                  );
                })}
              </ul>
            </>
          )}

          {closed.length > 0 && (
            <>
              <div className="list-head">
                <h2>Verkauft</h2>
                <button className="toggle-link" onClick={() => setShowClosed((v) => !v)}>{showClosed ? "ausblenden" : `${closed.length} anzeigen`}</button>
              </div>
              {showClosed && (
                <ul className="asset-list">
                  {closed.map((g) => (
                    <AssetRow key={g.symbol} symbol={g.symbol} name={displayName(g)} meta={<>{g.closed_lots} {g.closed_lots === 1 ? "Verkauf" : "Verkäufe"}</>}
                      top={{ text: signedMoney(g.realized, g.currency), tone: tone(g.realized) }} bottom={{ text: "Ergebnis" }} />
                  ))}
                </ul>
              )}
            </>
          )}
        </>
      )}

      {buying && <BuyDialog onClose={() => setBuying(false)} onSaved={load} />}
    </>
  );
}
