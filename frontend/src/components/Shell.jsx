import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { api } from "../api.js";

const NAV = [
  { to: "/", label: "Heute", end: true, icon: "M4 12 A8 8 0 0 1 20 12 M12 4 V2 M5.6 6.6 L4.2 5.2 M18.4 6.6 L19.8 5.2 M3 17 H21 M6 21 H18" },
  { to: "/watchlist", label: "Watchlist", icon: "M5 4 H19 V21 L12 17 L5 21 Z" },
  { to: "/chart", label: "Chart", icon: "M4 19 H20 M7 15 V9 M12 15 V5 M17 15 V11 M6 9 H8 M11 5 H13 M16 11 H18" },
  { to: "/alerts", label: "Alarme", icon: "M6 17 V11 A6 6 0 0 1 18 11 V17 L20 19 H4 Z M10 21 H14" },
  { to: "/settings", label: "Einstellungen", short: "Setup", icon: "M12 9 A3 3 0 1 0 12.01 9 M12 3 V5 M12 19 V21 M3 12 H5 M19 12 H21 M5.6 5.6 L7 7 M17 17 L18.4 18.4 M18.4 5.6 L17 7 M7 17 L5.6 18.4" },
];

/** Rahmen der App: Seitenleiste am Computer, Tabs am unteren Rand auf dem Handy. */
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

  useEffect(() => {
    const hit = [...NAV].reverse().find((n) => (n.end ? pathname === n.to : pathname.startsWith(n.to)));
    document.title = pathname.startsWith("/admin") ? "Administration · TradeHelper" : hit ? `${hit.label} · TradeHelper` : "TradeHelper";
  }, [pathname]);

  return (
    <div className="shell">
      <a className="skip-link" href="#inhalt">Zum Inhalt springen</a>
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M3 17 L9 11 L13 15 L21 7 M15 7 H21 V13" /></svg>
          </span>
          TradeHelper
        </div>
        <nav aria-label="Hauptmenü" className="nav">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end}>
              <svg viewBox="0 0 24 24" className="nav-icon" aria-hidden="true" focusable="false"><path d={n.icon} /></svg>
              <span className="nav-label">{n.label}</span>
              {n.short && <span className="nav-short" aria-hidden="true">{n.short}</span>}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className="muted small">{user.username}</span>
          <NavLink className="link" to="/admin">Administration</NavLink>
          <button className="link" onClick={onLogout}>Abmelden</button>
          {ver && (
            <div className="version-line">
              <span className="muted small">Version {ver.version}</span>
              {ver.update_available && <NavLink className="update-hint" to="/admin">Update verfügbar</NavLink>}
            </div>
          )}
        </div>
      </aside>
      <main className="main" id="inhalt" tabIndex={-1}>
        <div className="mobile-top">
          <span className="brand small-brand">TradeHelper</span>
          <span className="mobile-top-links">
            {ver?.update_available && <NavLink className="update-hint" to="/admin">Update</NavLink>}
            <NavLink className="link" to="/admin">Admin</NavLink>
            <button className="link" onClick={onLogout}>Abmelden</button>
          </span>
        </div>
        <div className="page" key={pathname}>{children}</div>
        <p className="disclaimer muted small">Regelbasierte, automatisch erzeugte Einschätzungen. Keine Anlageberatung.</p>
      </main>
    </div>
  );
}
