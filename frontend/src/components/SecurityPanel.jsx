import { useCallback, useEffect, useState } from "react";
import { api, getDevice, setDevice } from "../api.js";
import { dateTime } from "../fmt.js";
import Icon from "./Icon.jsx";
import Modal from "./Modal.jsx";
import { ErrorText } from "./ui.jsx";
import { RecoveryCodes, TwoFactorWizard } from "../pages/TwoFactorSetup.jsx";

/** Einstellungen → Sicherheit: Zwei-Faktor-Anmeldung, gemerkte Geräte, Wiederherstellungscodes. */
export default function SecurityPanel() {
  const [st, setSt] = useState(null);
  const [error, setError] = useState("");
  const [wizard, setWizard] = useState(false);
  const [confirm, setConfirm] = useState(null); // "recovery" | "disable"
  const [pw, setPw] = useState("");
  const [code, setCode] = useState("");
  const [codes, setCodes] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.get("/auth/2fa").then(setSt).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  async function forget(id) {
    await api.del(`/auth/2fa/devices/${id}`);
    load();
  }
  async function forgetAll() {
    await api.del("/auth/2fa/devices");
    setDevice(null);
    load();
  }
  async function submitConfirm(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (confirm === "recovery") {
        const r = await api.post("/auth/2fa/recovery", { password: pw, code });
        setCodes(r.recovery_codes);
      } else {
        await api.post("/auth/2fa/disable", { password: pw, code });
        setDevice(null);
      }
      setConfirm(null);
      setPw("");
      setCode("");
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!st) return <section className="panel" id="security"><h2>Sicherheit</h2><ErrorText error={error} /></section>;
  const thisDevice = getDevice();
  return (
    <section className="panel" id="security">
      <h2><Icon name="shield" /> Sicherheit</h2>
      <p className="muted small">Zwei-Faktor-Anmeldung: Passwort plus Code aus einer Authenticator-App. Gemerkte Geräte
        brauchen {st.device_days} Tage lang keinen Code.{st.required ? " Auf diesem Server ist sie Pflicht." : ""}</p>
      {st.enabled ? (
        <>
          <p><span className="status-dot ok" />Aktiv · {st.recovery_left} Wiederherstellungscodes übrig</p>
          <h3 style={{ margin: "1rem 0 0.4rem" }}>Gemerkte Geräte</h3>
          {st.devices.length ? (
            <ul className="device-list">
              {st.devices.map((d) => (
                <li key={d.id}>
                  <span><strong>{d.name || "Gerät"}</strong><span className="muted small"> · zuletzt {dateTime(d.last_used)} · bis {dateTime(d.expires_at)}</span></span>
                  <button className="link danger small" onClick={() => forget(d.id)}>Vergessen</button>
                </li>
              ))}
            </ul>
          ) : <p className="muted small">Keine – jede Anmeldung fragt nach dem Code.</p>}
          <div className="actions">
            {st.devices.length > 0 && <button className="btn" onClick={forgetAll}>Alle Geräte vergessen</button>}
            <button className="btn" onClick={() => setConfirm("recovery")}><Icon name="key" /> Neue Wiederherstellungscodes</button>
            <button className="btn" onClick={() => setWizard(true)}><Icon name="phone" /> Neues Handy</button>
            {!st.required && <button className="btn danger" onClick={() => setConfirm("disable")}>Ausschalten</button>}
          </div>
          {thisDevice && <p className="muted small">Dieses Gerät ist gemerkt.</p>}
        </>
      ) : (
        <>
          <p><span className="status-dot" />Nicht eingerichtet</p>
          <div className="actions"><button className="btn primary" onClick={() => setWizard(true)}><Icon name="shield" /> Jetzt einrichten</button></div>
        </>
      )}
      <ErrorText error={error} />
      {wizard && (
        <Modal title="Zwei-Faktor-Anmeldung" onClose={() => setWizard(false)} wide>
          <TwoFactorWizard onDone={() => { setWizard(false); load(); }} onCancel={() => setWizard(false)} />
        </Modal>
      )}
      {confirm && (
        <Modal title={confirm === "recovery" ? "Neue Wiederherstellungscodes" : "Zwei-Faktor-Anmeldung ausschalten"} onClose={() => setConfirm(null)}>
          <form onSubmit={submitConfirm} style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
            <p className="muted small">{confirm === "recovery" ? "Die bisherigen Codes werden ungültig." : "Danach reicht wieder das Passwort."} Zur Sicherheit:</p>
            <label>Passwort<input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" required /></label>
            <label>Code aus der App<input className="otp" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" required /></label>
            <ErrorText error={error} />
            <div className="actions"><button className="btn primary" disabled={busy}>Bestätigen</button><button type="button" className="btn" onClick={() => setConfirm(null)}>Abbrechen</button></div>
          </form>
        </Modal>
      )}
      {codes && (
        <Modal title="Deine neuen Codes" onClose={() => setCodes(null)}>
          <p className="muted small">Sicher aufbewahren – jeder Code gilt einmal.</p>
          <RecoveryCodes codes={codes} />
        </Modal>
      )}
    </section>
  );
}
