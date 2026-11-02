import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setToken } from "../api.js";

/** Anmeldung. Beim allerersten Aufruf wird hier das (einzige) Konto angelegt. */
export default function Login({ onLoggedIn }) {
  const navigate = useNavigate();
  const [setup, setSetup] = useState(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/auth/status").then((r) => setSetup(r.setup_required)).catch((e) => setError(e.message));
  }, []);

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (setup && password !== password2) {
      setError("Die Passwörter stimmen nicht überein.");
      return;
    }
    setBusy(true);
    try {
      const r = await api.post(setup ? "/auth/setup" : "/auth/login", { username, password });
      setToken(r.token);
      await onLoggedIn();
      navigate(setup ? "/settings" : "/");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <div className="login-art">
        <div className="brand login-brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M3 17 L9 11 L13 15 L21 7 M15 7 H21 V13" /></svg>
          </span>
          TradeHelper
        </div>
        <p>Watchlist, Chartanalyse, Alarme und jeden Morgen eine Einschätzung aufs Handy.</p>
        <svg className="login-chart" viewBox="0 0 300 120" aria-hidden="true">
          <polyline points="0,100 30,88 60,94 90,70 120,76 150,52 180,60 210,34 240,42 270,18 300,24" />
        </svg>
      </div>
      <form className="login-form" onSubmit={submit}>
        <h1>{setup ? "Willkommen" : "Anmelden"}</h1>
        {setup && <p className="muted">Lege dein Konto an. Danach ist die Anmeldung nur noch damit möglich.</p>}
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
          {busy ? "Einen Moment …" : setup ? "Konto anlegen" : "Anmelden"}
        </button>
        {!setup && setup !== null && (
          <p className="muted small">Passwort vergessen? Im Container: <code>./install.sh reset-login</code></p>
        )}
      </form>
    </div>
  );
}
