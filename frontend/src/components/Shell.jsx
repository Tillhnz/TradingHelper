import UpdateToast from "./UpdateToast.jsx";
import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api.js";
import WhatsNew from "./WhatsNew.jsx";
import { useMode } from "../mode.js";
import GlobalSearch from "./GlobalSearch.jsx";
import Icon from "./Icon.jsx";
import { loadTheme, resolvedTheme, saveTheme } from "../theme.js";

// Hauptmenü in zwei ruhigen Gruppen. „short“ = Beschriftung in der Handy-Leiste, mobile=false = nur am Computer
const NAV = [
  { to: "/", label: "Übersicht", end: true, icon: "grid", short: "Start" },
  { to: "/portfolio", label: "Portfolio", icon: "pie" },
  { to: "/watchlist", label: "Meine Werte", short: "Werte", icon: "star" },
  { to: "/markt", label: "Markt", icon: "globe" },
  { to: "/modell", label: "Modell", icon: "brain", mobile: false },
  { group: "Werkzeuge" },
  { to: "/charts", label: "Charts", icon: "activity", mobile: false },
  { to: "/depot", label: "Käufe & Blöcke", short: "Käufe", icon: "briefcase", mobile: false },
  { to: "/alerts", label: "Alarme", icon: "bell" },
  { to: "/settings", label: "Einstellungen", short: "Setup", icon: "sliders", mobile: false },
];

export function ModeSwitch() {
  const { mode, setMode } = useMode();
  return (
    <div className="mode-switch" role="group" aria-label="Ansicht">
      <button className={mode === "simple" ? "on" : ""} onClick={() => setMode("simple")} title="Übersichtlich, ohne Fachdetails">Einfach</button>
      <button className={mode === "pro" ? "on" : ""} onClick={() => setMode("pro")} title="Kerzen, Indikatoren und Kennzahlen">Profi</button>
    </div>
  );
}

export function ThemeSwitch() {
  const [pref, setPref] = useState(loadTheme);
  const pick = (p) => { setPref(p); saveTheme(p); };
  return (
    <div className="seg" role="group" aria-label="Farbmodus">
      {[["light", "Hell"], ["dark", "Dunkel"], ["system", "System"]].map(([k, l]) => (
        <button key={k} className={pref === k ? "on" : ""} onClick={() => pick(k)}>{l}</button>
      ))}
    </div>
  );
}

function ThemeToggle() {
  const [t, setT] = useState(() => resolvedTheme());
  useEffect(() => {
    const fn = (e) => setT(e.detail);
    window.addEventListener("th-theme", fn);
    return () => window.removeEventListener("th-theme", fn);
  }, []);
  const next = t === "dark" ? "light" : "dark";
  return (
    <button className="btn ghost icon-only theme-toggle" onClick={() => saveTheme(next)} title={next === "dark" ? "Dunkel" : "Hell"}
      aria-label={next === "dark" ? "Dunklen Modus einschalten" : "Hellen Modus einschalten"}>
      <Icon name={t === "dark" ? "sun" : "moon"} />
    </button>
  );
}

/** Rahmen der App: Seitenleiste am Computer, Kopfzeile mit Suche und Tabs am unteren Rand auf dem Handy. */
export default function Shell({ user, onLogout, children }) {
  const { pathname } = useLocation();
  const [ver, setVer] = useState(null);

  useEffect(() => {
    let stop = false;
    const load = () => api.get("/version").then((v) => { if (!stop) setVer(v); }).catch(() => {});
    load();
    const id = setInterval(load, 30 * 60 * 1000);
    return () => { stop = true; clearInterval(id); };
  }, []);

  // Adresse für Push-Links einmalig aus dem Browser übernehmen, falls noch nicht gesetzt
  useEffect(() => {
    if (!user.is_admin) return;
    api.get("/settings").then((r) => {
      const f = r.fields?.app_url;
      if (f && !f.value && !/^(localhost|127\.)/.test(window.location.hostname)) api.put("/settings", { app_url: window.location.origin }).catch(() => {});
    }).catch(() => {});
  }, [user.is_admin]);

  useEffect(() => {
    const items = NAV.filter((n) => n.to);
    const hit = [...items].reverse().find((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to)));
    if (!pathname.startsWith("/chart")) {
      document.title = pathname.startsWith("/admin") ? "Administration · TradeHelper" : hit ? `${hit.label} · TradeHelper` : "TradeHelper";
    }
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <div className="shell">
      <a className="skip-link" href="#inhalt">Zum Inhalt springen</a>
      <aside className="sidebar">
        <NavLink to="/" className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M3 17 L9 11 L13 15 L21 7 M15 7 H21 V13" /></svg>
          </span>
          TradeHelper
        </NavLink>
        <nav aria-label="Hauptmenü" className="nav">
          {NAV.map((n) => (n.group ? <div key={n.group} className="nav-group">{n.group}</div> : (
            <NavLink key={n.to} to={n.to} end={n.end} title={n.label} className={n.mobile === false ? "mobile-hide" : ""}>
              <Icon name={n.icon} className="nav-icon" />
              <span className="nav-label">{n.label}</span>
              {n.short && <span className="nav-short" aria-hidden="true">{n.short}</span>}
            </NavLink>
          )))}
        </nav>
        <div className="sidebar-foot">
          <span className="muted small">{user.username}{user.two_factor && <span title="Zwei-Faktor-Anmeldung aktiv"> · <Icon name="shield" /></span>}</span>
          {user.is_admin && <NavLink className="link small" to="/admin">Administration</NavLink>}
          <button className="link small" onClick={onLogout}>Abmelden</button>
          {ver && (
            <div className="version-line">
              <span className="muted small">Version {ver.version}</span>
              {ver.update_available && user.is_admin && <NavLink className="update-hint" to="/admin">Update verfügbar</NavLink>}
            </div>
          )}
        </div>
      </aside>
      <main className="main" id="inhalt" tabIndex={-1}>
        <div className="topbar">
          <NavLink to="/" className="brand small-brand mobile-only">
            <span className="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="M3 17 L9 11 L13 15 L21 7 M15 7 H21 V13" /></svg></span>
          </NavLink>
          <GlobalSearch />
          <div className="topbar-right">
            <ModeSwitch />
            <ThemeToggle />
            <NavLink to="/settings" className="btn ghost icon-only mobile-only" aria-label="Einstellungen"><Icon name="sliders" /></NavLink>
            {ver?.update_available && user.is_admin && <NavLink className="update-hint compact-only" to="/admin">Update</NavLink>}
          </div>
        </div>
        <div className="page" key={pathname}>{children}</div>
        <footer className="disclaimer muted small">
          Automatisch erzeugte Einschätzungen aus Regeln und einem lernenden Modell – keine Anlageberatung.
          <span className="compact-only">{user.is_admin && <> · <NavLink to="/admin">Administration</NavLink></>} · <button className="link small" onClick={onLogout}>Abmelden</button></span>
        </footer>
        {user.is_admin && <UpdateToast />}
      </main>
      <WhatsNew version={ver?.version} />
    </div>
  );
}
