import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Shell from "./components/Shell";
import { useAuth } from "./lib/auth";

const Work = lazy(() => import("./pages/Work"));
const Agents = lazy(() => import("./pages/Agents"));
const SettingsPage = lazy(() => import("./pages/Settings"));
const Screen = lazy(() => import("./pages/Screen"));
const Login = lazy(() => import("./pages/Login"));

function RouteFallback() {
  return (
    <div className="route-fallback" aria-busy="true">
      <div className="skeleton" style={{ height: 38, width: "42%" }} />
      <div className="grid g6" style={{ marginTop: 22 }}>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="skeleton" style={{ height: 96, opacity: 1 - i * 0.08 }} />
        ))}
      </div>
      <div className="skeleton" style={{ height: 300, marginTop: 16 }} />
    </div>
  );
}

export default function App() {
  const { user } = useAuth();

  return (
    <>
      <div className="aurora" aria-hidden>
        <span />
        <span />
        <span />
      </div>
      <div className="grain" aria-hidden />

      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/login" element={user ? <Navigate to="/work" replace /> : <Login />} />
          <Route path="/screen" element={user ? <Screen /> : <Navigate to="/login" replace />} />
          <Route element={user ? <Shell /> : <Navigate to="/login" replace />}>
            <Route path="/work" element={<Work />} />
            <Route path="/agents" element={<Agents />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
          <Route path="/" element={<Navigate to="/work" replace />} />
          <Route path="*" element={<Navigate to="/work" replace />} />
        </Routes>
      </Suspense>
    </>
  );
}
