import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, getDevice, setDevice, setToken } from "../api.js";

function Brand() {
  return (
    <div className="auth-brand">
      <span className="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24"><path d="M3 17 L9 11 L13 15 L21 7 M15 7 H21 V13" /></svg>
      </span>
      TradeHelper
    </div>
  );
}

/** Anmeldung: Passwort, danach (falls eingerichtet und das Gerät nicht gemerkt ist) der Code aus der App. */
export default function Login({ onLoggedIn }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [setup, setSetup] = useState(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [challenge, setChallenge] = useState(null);
  const [code, setCode] = useState("");
  const [remember, setRemember] = useState(true);
  const [useRecovery, setUseRecovery] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const codeRef = useRef(null);

  useEffect(() => {
    api.get("/auth/status").then((r) => setSetup(r.setup_required)).catch((e) => setError(e.message));
  }, []);

  useEffect(() => { if (challenge) codeRef.current?.focus(); }, [challenge, useRecovery]);

  async function finish(r) {
    setToken(r.token);
    if (r.device) setDevice(r.device);
    await onLoggedIn();
    // Kam der Aufruf aus einer Push-Nachricht (z. B. /?bericht=12), nach der Anmeldung dorthin
    navigate(setup ? "/settings" : location.state?.from || "/");
  }

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (setup && password !== password2) {
      setError("Die Passwörter stimmen nicht überein.");
      return;
    }
    setBusy(true);
    try {
      const r = await api.post(setup ? "/auth/setup" : "/auth/login", { username, password, device: getDevice() || undefined });
      if (r.two_factor) {
        setChallenge(r.challenge);
        setBusy(false);
        return;
      }
      await finish(r);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(e) {
    e?.preventDefault();
    setError("");
    setBusy(true);
    try {
      const r = await api.post("/auth/2fa/verify", { challenge, code: code.trim(), remember });
      if (r.recovery_left !== undefined && r.recovery_left <= 3) {
        window.alert(`Noch ${r.recovery_left} Wiederherstellungscodes übrig. Neue gibt es unter Einstellungen → Sicherheit.`);
      }
      await finish(r);
    } catch (err) {
      setError(err.message);
      if (/abgelaufen/.test(err.message)) setChallenge(null);
      setBusy(false);
    }
  }

  const onCode = (v) => {
    const clean = useRecovery ? v : v.replace(/\D/g, "").slice(0, 6);
    setCode(clean);
    if (!useRecovery && clean.length === 6 && !busy) setTimeout(() => document.getElementById("otp-form")?.requestSubmit(), 0);
  };

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <Brand />
        {!challenge ? (
          <form className="panel" onSubmit={submit}>
            <h1 className="auth-title">{setup ? "Willkommen" : "Schön, dass du da bist"}</h1>
            <p className="muted">{setup
              ? "Lege dein Konto an. Danach richtest du die Zwei-Faktor-Anmeldung ein; weitere Personen lädst du unter Administration ein."
              : "Melde dich an, um deine Depots, Werte und Einschätzungen zu sehen."}</p>
            <label>
              Benutzername
              <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required autoFocus />
            </label>
            <label>
              Passwort {setup && <span className="hint">mindestens 8 Zeichen</span>}
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                autoComplete={setup ? "new-password" : "current-password"} required minLength={setup ? 8 : 1} />
            </label>
            {setup && (
              <label>
                Passwort wiederholen
                <input type="password" value={password2} onChange={(e) => setPassword2(e.target.value)} autoComplete="new-password" required />
              </label>
            )}
            {error && <p className="error" role="alert">{error}</p>}
            <button className="btn primary" disabled={busy || setup === null}>
              {busy ? "Einen Moment …" : setup ? "Konto anlegen" : "Weiter"}
            </button>
            {!setup && setup !== null && (
              <p className="muted small">Passwort vergessen? Im Container: <code>./install.sh reset-login</code></p>
            )}
          </form>
        ) : (
          <form id="otp-form" className="panel" onSubmit={submitCode}>
            <h1 className="auth-title">Bestätigen</h1>
            <p className="muted">{useRecovery
              ? "Gib einen deiner Wiederherstellungscodes ein (jeder gilt nur einmal)."
              : "Gib den 6-stelligen Code aus deiner Authenticator-App ein."}</p>
            <label>
              {useRecovery ? "Wiederherstellungscode" : "Code"}
              <input ref={codeRef} className={useRecovery ? "" : "otp"} value={code} onChange={(e) => onCode(e.target.value)}
                inputMode={useRecovery ? "text" : "numeric"} autoComplete="one-time-code" placeholder={useRecovery ? "abcde-fghij" : "000000"}
                maxLength={useRecovery ? 12 : 6} required />
            </label>
            <label className="check">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              Dieses Gerät merken – hier 30 Tage ohne Code anmelden
            </label>
            {error && <p className="error" role="alert">{error}</p>}
            <button className="btn primary" disabled={busy || code.length < 6}>{busy ? "Prüfe …" : "Anmelden"}</button>
            <div className="actions" style={{ marginTop: 0 }}>
              <button type="button" className="link small" onClick={() => { setUseRecovery((x) => !x); setCode(""); }}>
                {useRecovery ? "Code aus der App verwenden" : "Handy nicht zur Hand? Wiederherstellungscode"}
              </button>
              <button type="button" className="link small" onClick={() => { setChallenge(null); setCode(""); setError(""); }}>Zurück</button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
