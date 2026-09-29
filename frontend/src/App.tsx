import { Navigate, Route, Routes } from "react-router-dom";
import Layout, { NAV } from "./components/Layout";
import { useAuth } from "./lib/auth";
import { LoginPage, RegisterPage } from "./pages/AuthPages";
import ComingSoon from "./pages/ComingSoon";
import Dashboard from "./pages/Dashboard";
import Markets from "./pages/Markets";
import Scanner from "./pages/Scanner";
import Signals from "./pages/Signals";
import Settings from "./pages/Settings";
import StockDetail from "./pages/StockDetail";

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="p-6 text-sm text-ink-400">Loading…</p>;
  return user ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route index element={<Dashboard />} />
        <Route path="settings" element={<Settings />} />
        <Route path="markets" element={<Markets />} />
        <Route path="stocks/:mic/:ticker" element={<StockDetail />} />
        <Route path="scanner" element={<Scanner />} />
        <Route path="signals" element={<Signals />} />
        {NAV.filter((n) => !["/", "/settings", "/markets", "/scanner", "/signals"].includes(n.to)).map((n) => (
          <Route key={n.to} path={n.to.slice(1)} element={<ComingSoon path={n.to} />} />
        ))}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
