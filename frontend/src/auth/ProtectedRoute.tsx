import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";

export function ProtectedRoute() {
  const { state } = useAuth();
  const location = useLocation();
  if (state.status === "loading") return <p className="center-note" role="status">Loading…</p>;
  if (state.status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

export function PublicOnlyRoute() {
  const { state } = useAuth();
  const location = useLocation();
  if (state.status === "loading") return <p className="center-note" role="status">Loading…</p>;
  if (state.status === "authenticated") {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from && from.startsWith("/") ? from : "/"} replace />;
  }
  return <Outlet />;
}
