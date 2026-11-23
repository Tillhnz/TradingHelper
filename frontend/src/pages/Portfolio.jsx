import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, fileToBase64 } from "../api.js";
import { useCachedGet } from "../cache.js";
import Icon from "../components/Icon.jsx";
import Modal from "../components/Modal.jsx";
import { ErrorText, Loading, RefreshState } from "../components/ui.jsx";
import { LineArea, Stack } from "../components/viz.jsx";
import { dateTime, money, num, pct, signedMoney, tone } from "../fmt.js";

const STATUS = { ok: "aktuell", new: "noch nicht abgerufen", tan: "wartet auf Freigabe", tan_needed: "Freigabe nötig", error: "Fehler" };

// ---------- Depot verbinden ----------
function ConnectDialog({ onClose, onCreated }) {
  const banksQ = useCachedGet("/portfolio/banks");
  const [bank, setBank] = useState(null);
  const [f, setF] = useState({ label: "", blz: "", login: "", customer_id: "", url: "", pin: "", save_pin: false });
  const [advanced, setAdvanced] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const banks = banksQ.data?.banks || [];
  const b = banks.find((x) => x.id === bank);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api.post("/portfolio/accounts", { bank, ...f, blz: f.blz || b.blz || "", url: f.url || b.url || "" });
      onCreated(r.id, b, f.pin);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Modal title="Depot verbinden" onClose={onClose} wide>
      <p className="muted small">TradeHelper liest nur – es kann keine Aufträge erteilen und kein Geld bewegen.</p>
      {!banksQ.data ? <Loading /> : (
        <div className="bank-pick">
          {banks.map((x) => (
            <button key={x.id} className={bank === x.id ? "on" : ""} onClick={() => { setBank(x.id); setF((v) => ({ ...v, label: x.name, blz: x.blz || "" })); }}>
              <strong>{x.name}</strong><small>{x.kind === "fints" ? "Bankzugang (FinTS), automatisch" : "Import von CSV/PDF"}</small>
            </button>
          ))}
        </div>
      )}
      {b && b.kind === "fints" && (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
          {!banksQ.data.fints_ready && (
            <p className="note small"><Icon name="info" /> Für den Bankzugang fehlt noch die kostenlose FinTS-Produkt-Registrierungsnummer
              (Einstellungen → Bankzugang). Die Verbindung lässt sich trotzdem schon anlegen.</p>
          )}
          {b.setup_hint && <p className="muted small">{b.setup_hint}</p>}
          <div className="form-grid">
            <label>Name<input value={f.label} onChange={set("label")} /></label>
            {!b.blz && <label>Bankleitzahl<input value={f.blz} onChange={set("blz")} inputMode="numeric" placeholder="8 Ziffern" required /></label>}
            <label>{b.login_label} <span className="hint">{b.login_hint}</span><input value={f.login} onChange={set("login")} autoComplete="username" required /></label>
            <label>{b.pin_label}<input type="password" value={f.pin} onChange={set("pin")} autoComplete="current-password" /></label>
          </div>
          <label className="check"><input type="checkbox" checked={f.save_pin} onChange={set("save_pin")} />
            PIN verschlüsselt speichern – dann ruft TradeHelper das Depot regelmäßig selbst ab</label>
          <button type="button" className="link small" style={{ alignSelf: "flex-start" }} onClick={() => setAdvanced((x) => !x)}>{advanced ? "Weniger" : "Erweitert (FinTS-Adresse, Kundennummer)"}</button>
          {advanced && (
            <div className="form-grid">
              <label>FinTS-Adresse<input value={f.url || b.url || ""} onChange={set("url")} /></label>
              <label>Kundennummer <span className="hint">nur falls abweichend</span><input value={f.customer_id} onChange={set("customer_id")} /></label>
              {b.blz && <label>Bankleitzahl<input value={f.blz} onChange={set("blz")} /></label>}
            </div>
          )}
          <p className="muted small">{b.tan_hint}. Die Bank fragt etwa alle 90 Tage nach einer neuen Freigabe.</p>
          <ErrorText error={error} />
          <div className="actions"><button className="btn primary" disabled={busy}>{busy ? "Lege an …" : "Verbinden und abrufen"}</button></div>
        </form>
      )}
      {b && b.kind === "import" && (
        <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
          <p className="muted small">{b.import_hint}</p>
          <label>Name<input value={f.label} onChange={set("label")} /></label>
          <ErrorText error={error} />
          <div className="actions"><button className="btn primary" disabled={busy}>Anlegen und Dateien wählen</button></div>
        </form>
      )}
    </Modal>
  );
}

// ---------- Abrufen mit Freigabe ----------
function SyncDialog({ account, pin: initialPin, onClose, onDone }) {
  const [pin, setPin] = useState(initialPin || "");
  const [step, setStep] = useState(account.pin_saved || initialPin ? "run" : "pin");
  const [tan, setTan] = useState("");
  const [ch, setCh] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const started = useRef(false);

  async function run(p = pin) {
    setBusy(true);
    setError("");
    try {
      handle(await api.post(`/portfolio/accounts/${account.id}/sync`, { pin: p }));
    } catch (e) { setError(e.message); setStep("pin"); } finally { setBusy(false); }
  }
  function handle(r) {
    if (r.status === "tan") { setCh(r); setTan(""); setStep("tan"); } else { setResult(r); setStep("done"); onDone(); }
  }
  async function sendTan(e) {
    e?.preventDefault();
    setBusy(true);
    setError("");
    try {
      handle(await api.post(`/portfolio/accounts/${account.id}/tan`, { session: ch.session, tan }));
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }
  useEffect(() => {
    if (step === "run" && !started.current) { started.current = true; run(); }
  }, [step]); // eslint-disable-line react-hooks/exhaustive-deps
  function close() {
    if (ch?.session && step === "tan") api.del(`/portfolio/tan/${ch.session}`).catch(() => {});
    onClose();
  }

  return (
    <Modal title={`${account.label} abrufen`} onClose={close}>
      {step === "pin" && (
        <form onSubmit={(e) => { e.preventDefault(); setStep("run"); started.current = true; run(pin); }} style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
          <label>PIN<input type="password" value={pin} onChange={(e) => setPin(e.target.value)} autoFocus required /></label>
          <ErrorText error={error} />
          <div className="actions"><button className="btn primary" disabled={busy}>Abrufen</button></div>
        </form>
      )}
      {step === "run" && <Loading text="Verbinde mit der Bank …" />}
      {step === "tan" && ch && (
        <form className="tan-box" onSubmit={sendTan}>
          <p style={{ margin: 0 }}>{ch.challenge.text}</p>
          {ch.challenge.image && <img src={ch.challenge.image} alt="photoTAN-Grafik zum Scannen" />}
          {ch.challenge.decoupled ? (
            <>
              <p className="muted small">Öffne die App deiner Bank und gib den Zugriff frei. Danach hier bestätigen.</p>
              <button className="btn primary" disabled={busy}>{busy ? "Prüfe …" : "In der App freigegeben"}</button>
            </>
          ) : (
            <>
              <label style={{ width: "100%" }}>TAN<input value={tan} onChange={(e) => setTan(e.target.value)} inputMode="numeric" autoFocus required /></label>
              <button className="btn primary" disabled={busy || !tan}>{busy ? "Sende …" : "Bestätigen"}</button>
            </>
          )}
          <ErrorText error={error} />
        </form>
      )}
      {step === "done" && result && (
        <>
          <p><Icon name="check" /> {result.holdings} Positionen aus {result.accounts} {result.accounts === 1 ? "Konto" : "Konten"} übernommen.
            {result.assigned ? ` ${result.assigned} erfasste Käufe wurden diesem Depot zugeordnet.` : ""}</p>
          <div className="actions"><button className="btn primary" onClick={onClose}>Fertig</button></div>
        </>
      )}
    </Modal>
  );
}

// ---------- Import ----------
function ImportDialog({ account, onClose, onDone }) {
  const [files, setFiles] = useState([]);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const input = useRef(null);

  async function read(list) {
    const fs = [...list].slice(0, 40);
    setFiles(fs);
    setBusy(true);
    setError("");
    try {
      const payload = await Promise.all(fs.map(async (f) => ({ name: f.name, content: await fileToBase64(f) })));
      setPreview(await api.post(`/portfolio/accounts/${account.id}/import/preview`, { files: payload }));
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function commit() {
    setBusy(true);
    setError("");
    try {
      const r = await api.post(`/portfolio/accounts/${account.id}/import`, {
        trades: preview.trades.filter((t) => !t.duplicate), holdings: preview.holdings });
      setResult(r);
      onDone();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  const fresh = preview?.trades.filter((t) => !t.duplicate) || [];

  return (
    <Modal title={`Import: ${account.label}`} onClose={onClose} wide>
      {!preview && !result && (
        <>
          <div className={`dropzone ${over ? "over" : ""}`} onClick={() => input.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); read(e.dataTransfer.files); }}>
            <Icon name="upload" size="1.6em" />
            <p style={{ margin: "0.4rem 0 0" }}><strong>CSV- oder PDF-Dateien hierher ziehen</strong> oder klicken</p>
            <p className="small">Umsatzliste (CSV) oder Wertpapierabrechnungen (PDF), auch viele auf einmal</p>
            <input ref={input} type="file" accept=".csv,.pdf,.txt" multiple hidden onChange={(e) => read(e.target.files)} />
          </div>
          {busy && <Loading text={`Lese ${files.length} ${files.length === 1 ? "Datei" : "Dateien"} …`} />}
        </>
      )}
      {preview && !result && (
        <>
          <p>{fresh.length} neue Käufe/Verkäufe erkannt{preview.trades.length - fresh.length ? `, ${preview.trades.length - fresh.length} schon importiert` : ""}
            {preview.holdings.length ? ` · ${preview.holdings.length} Bestände` : ""}.</p>
          {preview.trades.length > 0 && (
            <div className="table-wrap" style={{ maxHeight: 320, overflow: "auto" }}>
              <table className="table">
                <thead><tr><th>Datum</th><th>Art</th><th>Wert</th><th className="num">Stück</th><th className="num">Kurs</th><th className="num">Gebühren</th></tr></thead>
                <tbody>
                  {preview.trades.map((t) => (
                    <tr key={t.fingerprint} className={t.duplicate ? "inactive" : ""}>
                      <td>{t.day.split("-").reverse().join(".")}{t.time ? ` ${t.time}` : ""}</td>
                      <td><span className={`badge ${t.side === "buy" ? "buy" : "sell"}`}>{t.side === "buy" ? "Kauf" : "Verkauf"}</span></td>
                      <td>{t.name || t.isin}<div className="muted small">{t.isin}{t.duplicate ? " · schon importiert" : ""}</div></td>
                      <td className="num">{num(t.quantity, t.quantity % 1 ? 3 : 0)}</td>
                      <td className="num">{money(t.price, t.currency)}</td>
                      <td className="num">{money(t.fees, t.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {preview.holdings.length > 0 && (
            <ul className="mini-list" style={{ marginTop: "0.75rem" }}>
              {preview.holdings.map((h) => <li key={h.isin}><span className="two"><span className="nm">{h.name || h.isin}</span><span className="sub">{h.isin}</span></span><span className="rt">{num(h.quantity, 3)} Stück</span></li>)}
            </ul>
          )}
          {preview.skipped.length > 0 && (
            <details style={{ marginTop: "0.75rem" }}><summary className="muted small">{preview.skipped.length} Zeilen übersprungen</summary>
              <ul className="small muted">{preview.skipped.slice(0, 30).map((s) => <li key={s}>{s}</li>)}</ul></details>
          )}
          <ErrorText error={error} />
          <div className="actions">
            <button className="btn primary" onClick={commit} disabled={busy || (!fresh.length && !preview.holdings.length)}>{busy ? "Übernehme …" : "Übernehmen"}</button>
            <button className="btn" onClick={() => setPreview(null)}>Andere Dateien</button>
          </div>
        </>
      )}
      {result && (
        <>
          <p><Icon name="check" /> {result.created} Käufe angelegt, {result.closed} Blöcke geschlossen{result.holdings ? `, ${result.holdings} Bestände übernommen` : ""}.
            {result.duplicates ? ` ${result.duplicates} waren schon da.` : ""}</p>
          {result.problems?.length > 0 && <ul className="small" style={{ color: "var(--amber)" }}>{result.problems.map((p) => <li key={p}>{p}</li>)}</ul>}
          <div className="actions"><button className="btn primary" onClick={onClose}>Fertig</button><Link className="btn" to="/depot">Käufe ansehen</Link></div>
        </>
      )}
      {error && !preview && <ErrorText error={error} />}
    </Modal>
  );
}

// ---------- Seite ----------
export default function Portfolio() {
  const q = useCachedGet("/portfolio");
  const pf = q.data;
  const [by, setBy] = useState("type");
  const [connect, setConnect] = useState(false);
  const [sync, setSync] = useState(null);
  const [imp, setImp] = useState(null);
  const [error, setError] = useState("");

  function created(id, bank, pin) {
    setConnect(false);
    q.reload();
    const acc = { id, label: bank.name, pin_saved: false };
    if (bank.kind === "fints") setSync({ account: acc, pin });
    else setImp(acc);
  }
  async function remove(a) {
    if (!window.confirm(`Verbindung „${a.label}“ löschen? Abgerufene Bestände verschwinden, importierte Käufe bleiben.`)) return;
    try { await api.del(`/portfolio/accounts/${a.id}`); q.reload(); } catch (e) { setError(e.message); }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Portfolio</h1>
          <p className="muted">Alle Depots zusammen – nur lesend verbunden. <RefreshState q={q} /></p>
        </div>
        <div className="actions" style={{ marginTop: 0 }}>
          <Link className="btn" to="/depot"><Icon name="briefcase" /> Käufe & Blöcke</Link>
          <button className="btn primary" onClick={() => setConnect(true)}><Icon name="plus" /> Depot verbinden</button>
        </div>
      </div>
      <ErrorText error={error || q.error} />
      {!pf && !q.error && <Loading text="Rechne alle Depots zusammen …" />}
      {pf && (
        <>
          <div className="pf-head">
            <section className="wcard">
              <span className="wtitle"><Icon name="wallet" /> Gesamtvermögen</span>
              <div className="kpi">{money(pf.value, pf.currency)}</div>
              <div className="kpi-sub">
                {pf.day_change_pct != null && <span className={`delta ${tone(pf.day_change_pct)}`}>{signedMoney(pf.day_change, pf.currency)} · {pct(pf.day_change_pct)} heute</span>}
                {pf.pl_pct != null && <span className={tone(pf.pl)}>{signedMoney(pf.pl, pf.currency)} ({pct(pf.pl_pct, 1)}) seit Kauf</span>}
              </div>
              <LineArea values={(pf.history || []).map((h) => h.value)} height={110} />
            </section>
            <section className="wcard">
              <div className="whead"><span className="wtitle"><Icon name="pie" /> Aufteilung</span>
                <div className="seg">{[["type", "Art"], ["account", "Depot"], ["country", "Land"]].map(([k, l]) => <button key={k} className={by === k ? "on" : ""} onClick={() => setBy(k)}>{l}</button>)}</div>
              </div>
              {pf.allocation?.[by]?.length ? <Stack items={pf.allocation[by]} /> : <p className="wempty">Noch keine Bestände.</p>}
            </section>
          </div>
          {pf.hints?.map((h) => <p key={h.text} className="note small"><Icon name="alert" /> {h.text}</p>)}

          <h2 className="section-title">Depots</h2>
          <div className="acc-grid">
            {pf.accounts.map((a) => (
              <div key={a.id} className="acc">
                <header><strong>{a.label}</strong>{a.bank_name !== a.label && <span className="muted small">{a.bank_name}</span>}</header>
                <span className="val">{money(a.value, pf.currency)}</span>
                <span className="small muted"><span className={`status-dot ${a.status}`} />{STATUS[a.status] || a.status}{a.last_sync ? ` · ${dateTime(a.last_sync)}` : ""} · {a.positions} Positionen</span>
                {a.last_error && a.status === "error" && <span className="small error">{a.last_error}</span>}
                <div className="actions">
                  {a.kind === "fints"
                    ? <button className="btn small" onClick={() => setSync({ account: a })}><Icon name="refresh" /> Abrufen</button>
                    : <button className="btn small" onClick={() => setImp(a)}><Icon name="upload" /> Importieren</button>}
                  <button className="link danger small" onClick={() => remove(a)}>Löschen</button>
                </div>
              </div>
            ))}
            <button className="acc add" onClick={() => setConnect(true)}><Icon name="plus" size="1.4em" /> Depot verbinden</button>
          </div>

          {pf.lines.length > 0 && (
            <>
              <h2 className="section-title">Positionen</h2>
              <div className="table-wrap">
                <table className="table pf-table">
                  <thead><tr><th>Wert</th><th className="hide-sm">Depot</th><th className="num">Stück</th><th className="num">Kurs</th><th className="num">Wert</th><th className="num hide-sm">Anteil</th><th className="num">Seit Kauf</th><th className="num hide-sm">Heute</th></tr></thead>
                  <tbody>
                    {pf.lines.map((x) => (
                      <tr key={`${x.account_id}-${x.symbol || x.isin}`}>
                        <td className="nm">{x.symbol ? <Link className="sym" to={`/chart/${encodeURIComponent(x.symbol)}`}>{x.name || x.symbol}</Link> : x.name}
                          <div className="acc-tag">{x.type}{x.lots > 1 ? ` · ${x.lots} Blöcke` : ""}</div></td>
                        <td className="hide-sm muted small">{x.account}</td>
                        <td className="num">{num(x.quantity, x.quantity % 1 ? 3 : 0)}</td>
                        <td className="num">{money(x.price, pf.currency)}</td>
                        <td className="num"><strong>{money(x.value, pf.currency)}</strong></td>
                        <td className="num hide-sm">{x.weight != null ? `${num(x.weight, 1)} %` : "–"}</td>
                        <td className={`num ${tone(x.pl)}`}>{x.pl != null ? <>{signedMoney(x.pl, pf.currency)}<div className="small">{pct(x.pl_pct, 1)}</div></> : "–"}</td>
                        <td className={`num hide-sm ${tone(x.day_change_pct)}`}>{pct(x.day_change_pct)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
      {connect && <ConnectDialog onClose={() => setConnect(false)} onCreated={created} />}
      {sync && <SyncDialog account={sync.account} pin={sync.pin} onClose={() => { setSync(null); q.reload(); }} onDone={() => q.reload()} />}
      {imp && <ImportDialog account={imp} onClose={() => { setImp(null); q.reload(); }} onDone={() => q.reload()} />}
    </>
  );
}
