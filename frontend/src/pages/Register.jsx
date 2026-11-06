import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, setToken } from "../api.js";

/** Konto über einen Einladungslink anlegen. */
export default function Register({ onLoggedIn }) {
  const { token } = useParams();
  const navigate = useNavigate();
  const [invite, setInvite] = useState(null);
  const [error, setError] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get(`/auth/invite/${encodeURIComponent(token)}`).then(setInvite).catch((e) => setError(e.message));
  }, [token]);

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (password !== password2) {
      setError("Die Passwörter stimmen nicht überein.");
      return;
    }
    setBusy(true);
    try {
      const r = await api.post("/auth/register", { token, username, password });
      setToken(r.token);
      await onLoggedIn();
      navigate("/");
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
      {invite ? (
        <form className="login-form" onSubmit={submit}>
          <h1>Willkommen</h1>
          <p className="muted">
            {invite.invited_by ? <><strong>{invite.invited_by}</strong> hat dich eingeladen. </> : null}
            Lege dein Konto an. Watchlist, Depot und Alarme gehören nur dir – niemand sonst sieht sie.
          </p>
          <label>
            Benutzername
            <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required autoFocus maxLength={64} />
          </label>
          <label>
            Passwort <span className="hint">mindestens 8 Zeichen</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" required minLength={8} />
          </label>
          <label>
            Passwort wiederholen
            <input type="password" value={password2} onChange={(e) => setPassword2(e.target.value)} autoComplete="new-password" required />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn primary" disabled={busy}>{busy ? "Einen Moment …" : "Konto anlegen"}</button>
        </form>
      ) : (
        <div className="login-form">
          <h1>Einladung</h1>
          {error ? <p className="error" role="alert">{error}</p> : <p className="muted">Prüfe die Einladung …</p>}
          {error && <p className="muted small">Bitte um einen neuen Link. <Link to="/login">Zur Anmeldung</Link></p>}
        </div>
      )}
    </div>
  );
}
