import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api.js";
import { useMode } from "../mode.js";
import GlobalSearch from "./GlobalSearch.jsx";

const NAV = [
  { to: "/", label: "Übersicht", end: true, icon: "M3 11 L12 4 L21 11 V20 H14 V14 H10 V20 H3 Z" },
  { to: "/watchlist", label: "Meine Werte", short: "Werte", icon: "M12 3 L14.6 8.6 L20.8 9.3 L16.2 13.5 L17.5 19.6 L12 16.5 L6.5 19.6 L7.8 13.5 L3.2 9.3 L9.4 8.6 Z" },
  { to: "/charts", label: "Charts", icon: "M4 20 V4 M4 20 H20 M7 15 L11 10 L14 13 L19 7 M16 7 H19 V10" },
  { to: "/depot", label: "Depot", icon: "M3 7 H21 V19 H3 Z M3 11 H21 M8 7 V5 H16 V7 M7 15 H11" },
  { to: "/alerts", label: "Alarme", icon: "M6 17 V11 A6 6 0 0 1 18 11 V17 L20 19 H4 Z M10 21 H14" },
  { to: "/settings", label: "Einstellungen", short: "Setup", icon: "M12 9 A3 3 0 1 0 12.01 9 M12 3 V5 M12 19 V21 M3 12 H5 M19 12 H21 M5.6 5.6 L7 7 M17 17 L18.4 18.4 M18.4 5.6 L17 7 M7 17 L5.6 18.4" },
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
    const hit = [...NAV].reverse().find((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to)));
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
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} title={n.label}>
              <svg viewBox="0 0 24 24" className="nav-icon" aria-hidden="true" focusable="false"><path d={n.icon} /></svg>
              <span className="nav-label">{n.label}</span>
              {n.short && <span className="nav-short" aria-hidden="true">{n.short}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <ModeSwitch />
          <span className="muted small">Angemeldet als {user.username}</span>
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
          <div className="topbar-right compact-only">
            <ModeSwitch />
            {ver?.update_available && user.is_admin && <NavLink className="update-hint" to="/admin">Update</NavLink>}
          </div>
        </div>
        <div className="page" key={pathname}>{children}</div>
        <footer className="disclaimer muted small">
          Regelbasierte, automatisch erzeugte Einschätzungen – keine Anlageberatung.
          <span className="compact-only">{user.is_admin && <> · <NavLink to="/admin">Administration</NavLink></>} · <button className="link small" onClick={onLogout}>Abmelden</button></span>
        </footer>
      </main>
    </div>
  );
}
