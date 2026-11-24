import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, clearToken, getToken, setNeeds2faHandler, setUnauthorizedHandler } from "./api.js";
import Shell from "./components/Shell.jsx";
import { loadMode, ModeContext, saveMode } from "./mode.js";
import Login from "./pages/Login.jsx";
import Home from "./pages/Home.jsx";
import Watchlist from "./pages/Watchlist.jsx";
import ChartPage from "./pages/ChartPage.jsx";
import Alerts from "./pages/Alerts.jsx";
import Depot from "./pages/Depot.jsx";
import Shadow from "./pages/Shadow.jsx";
import Settings from "./pages/Settings.jsx";
import Admin from "./pages/Admin.jsx";
import Charts from "./pages/Charts.jsx";
import Register from "./pages/Register.jsx";
import Portfolio from "./pages/Portfolio.jsx";
import Markt from "./pages/Markt.jsx";
import Analyse from "./pages/Analyse.jsx";
import Modell from "./pages/Modell.jsx";
import TwoFactorSetup from "./pages/TwoFactorSetup.jsx";
import { currentTheme } from "./theme.js";

export default function App() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(!!getToken());
  const [mode, setModeState] = useState(loadMode);
  const [theme, setTheme] = useState(currentTheme);
  const modeValue = useMemo(() => ({ mode, setMode: (m) => { saveMode(m); setModeState(m); } }), [mode]);

  // Charts zeichnen auf eine Zeichenfläche: beim Wechsel hell/dunkel die Seite neu aufbauen
  useEffect(() => {
    const fn = (e) => setTheme(e.detail);
    window.addEventListener("th-theme", fn);
    return () => window.removeEventListener("th-theme", fn);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    navigate("/login");
  }, [navigate]);

  const loadUser = useCallback(async () => {
    try {
      setUser(await api.get("/me"));
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      navigate("/login");
    });
    setNeeds2faHandler(() => setUser((u) => (u ? { ...u, needs_2fa_setup: true } : u)));
    if (getToken()) loadUser();
  }, [loadUser, navigate]);

  if (loading) return <div className="center muted">Lade …</div>;

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<Login onLoggedIn={loadUser} />} />
        <Route path="/einladung/:token" element={<Register onLoggedIn={loadUser} />} />
        <Route path="*" element={<Navigate to="/login" replace state={{ from: window.location.pathname + window.location.search }} />} />
      </Routes>
    );
  }

  // Pflicht-2FA: erst einrichten, dann geht es weiter
  if (user.needs_2fa_setup) {
    return <TwoFactorSetup required user={user} onDone={loadUser} onLogout={logout} />;
  }

  return (
    <ModeContext.Provider value={modeValue}>
      <Shell user={user} onLogout={logout}>
        <Routes key={theme}>
          <Route path="/" element={<Home user={user} />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/analyse" element={<Analyse />} />
          <Route path="/markt" element={<Markt />} />
          <Route path="/modell" element={<Modell user={user} />} />
          <Route path="/chart" element={<Navigate to="/watchlist" replace />} />
          <Route path="/chart/:symbol" element={<ChartPage />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/depot" element={<Depot />} />
          <Route path="/depot/schatten" element={<Shadow />} />
          <Route path="/settings" element={<Settings user={user} />} />
          <Route path="/charts" element={<Charts />} />
          <Route path="/charts/:symbol" element={<Charts />} />
          <Route path="/admin" element={user.is_admin ? <Admin /> : <Navigate to="/" replace />} />
          <Route path="/login" element={<Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Shell>
    </ModeContext.Provider>
  );
}
