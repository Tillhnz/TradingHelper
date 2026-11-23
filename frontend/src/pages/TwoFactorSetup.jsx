import { useEffect, useState } from "react";
import { api, setDevice } from "../api.js";
import Icon from "../components/Icon.jsx";
import { ErrorText, Loading } from "../components/ui.jsx";

/** Codes zum Ausdrucken oder Abspeichern. */
export function RecoveryCodes({ codes }) {
  const [copied, setCopied] = useState(false);
  const text = codes.join("\n");
  async function copy() {
    try { await navigator.clipboard.writeText(text); setCopied(true); } catch { /* Browser ohne Zwischenablage */ }
  }
  function download() {
    const blob = new Blob([`TradeHelper – Wiederherstellungscodes\nJeder Code gilt einmal.\n\n${text}\n`], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "tradehelper-wiederherstellungscodes.txt";
    a.click();
    URL.revokeObjectURL(a.href);
  }
  return (
    <>
      <div className="codes">{codes.map((c) => <span key={c}>{c}</span>)}</div>
      <div className="actions" style={{ marginTop: "0.5rem" }}>
        <button type="button" className="btn" onClick={copy}><Icon name="copy" /> {copied ? "Kopiert" : "Kopieren"}</button>
        <button type="button" className="btn" onClick={download}><Icon name="upload" /> Als Datei sichern</button>
      </div>
    </>
  );
}

/**
 * Zwei-Faktor-Anmeldung einrichten: QR-Code scannen, Code bestätigen, Wiederherstellungscodes sichern.
 * required = Pflicht auf diesem Server (dann ohne „Später“).
 */
export function TwoFactorWizard({ onDone, required = false, onCancel }) {
  const [data, setData] = useState(null);
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showSecret, setShowSecret] = useState(false);

  useEffect(() => {
    api.post("/auth/2fa/setup").then(setData).catch((e) => setError(e.message));
  }, []);

  async function enable(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api.post("/auth/2fa/enable", { pending: data.pending, code, remember: true });
      if (r.device) setDevice(r.device);
      setCodes(r.recovery_codes);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (codes) {
    return (
      <div className="panel" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
        <h2><Icon name="shield" /> Eingerichtet</h2>
        <p>Bewahre diese <strong>Wiederherstellungscodes</strong> sicher auf (z. B. im Passwortmanager). Damit kommst du
          auch ohne Handy hinein – jeder Code gilt einmal. Dieses Gerät ist gemerkt.</p>
        <RecoveryCodes codes={codes} />
        <div className="actions"><button className="btn primary" onClick={onDone}>Fertig</button></div>
      </div>
    );
  }
  if (!data) return error ? <ErrorText error={error} /> : <Loading text="Erzeuge Schlüssel …" />;
  return (
    <form className="panel" onSubmit={enable}>
      <h2><Icon name="shield" /> Zwei-Faktor-Anmeldung einrichten</h2>
      <p className="muted">Zusätzlich zum Passwort fragt TradeHelper nach einem Code aus einer Authenticator-App
        (z. B. 2FAS, Aegis, Google oder Microsoft Authenticator, 1Password, Bitwarden). Gemerkte Geräte fragen 30 Tage lang nicht.</p>
      <div className="steps-2fa">
        <div className="qr" aria-label="QR-Code für die Authenticator-App">
          {data.qr_svg ? <span dangerouslySetInnerHTML={{ __html: data.qr_svg }} style={{ display: "contents" }} />
            : <span className="muted small" style={{ textAlign: "center" }}>QR-Code nicht verfügbar – Schlüssel abtippen</span>}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
          <p style={{ margin: 0 }}><strong>1.</strong> QR-Code mit der App scannen.
            {" "}<button type="button" className="link" onClick={() => setShowSecret((x) => !x)}>{showSecret ? "Schlüssel ausblenden" : "Scannen geht nicht?"}</button></p>
          {showSecret && <div className="secret">{data.secret_grouped}</div>}
          <p style={{ margin: 0 }}><strong>2.</strong> Den angezeigten 6-stelligen Code eingeben:</p>
          <input className="otp" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
            inputMode="numeric" autoComplete="one-time-code" placeholder="000000" required aria-label="Code aus der App" />
          <ErrorText error={error} />
          <div className="actions" style={{ marginTop: 0 }}>
            <button className="btn primary" disabled={busy || code.length !== 6}>{busy ? "Prüfe …" : "Aktivieren"}</button>
            {!required && onCancel && <button type="button" className="btn" onClick={onCancel}>Abbrechen</button>}
          </div>
        </div>
      </div>
    </form>
  );
}

/** Ganzseitig, wenn 2FA auf dem Server Pflicht ist und noch fehlt. */
export default function TwoFactorSetup({ user, onDone, onLogout, required }) {
  return (
    <div className="auth-wrap">
      <div className="auth-card" style={{ width: "min(640px, 100%)" }}>
        <div className="auth-brand">
          <span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 17 L9 11 L13 15 L21 7 M15 7 H21 V13" /></svg></span>
          TradeHelper
        </div>
        <h1 className="auth-title">Noch ein Schritt, {user.username}</h1>
        <p className="muted">Auf diesem Server ist die Zwei-Faktor-Anmeldung Pflicht. Das dauert eine Minute und schützt
          deine Depotdaten zusätzlich.</p>
        <TwoFactorWizard required={required} onDone={onDone} />
        <button className="link small" onClick={onLogout} style={{ alignSelf: "flex-start" }}>Abmelden</button>
      </div>
    </div>
  );
}
