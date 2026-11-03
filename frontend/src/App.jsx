import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { api, clearToken, getToken, setUnauthorizedHandler } from "./api.js";
import Shell from "./components/Shell.jsx";
import Login from "./pages/Login.jsx";
import Home from "./pages/Home.jsx";
import Watchlist from "./pages/Watchlist.jsx";
import ChartPage from "./pages/ChartPage.jsx";
import Alerts from "./pages/Alerts.jsx";
import Depot from "./pages/Depot.jsx";
import Settings from "./pages/Settings.jsx";
import Admin from "./pages/Admin.jsx";

export default function App() {
  const navigate = useNavigate();
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(!!getToken());

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
    if (getToken()) loadUser();
  }, [loadUser, navigate]);

  if (loading) return <div className="center muted">Lade …</div>;

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<Login onLoggedIn={loadUser} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Shell user={user} onLogout={logout}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/watchlist" element={<Watchlist />} />
        <Route path="/chart" element={<ChartPage />} />
        <Route path="/chart/:symbol" element={<ChartPage />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/depot" element={<Depot />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
