import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export function Layout() {
  const { state, logout } = useAuth();
  const [busy, setBusy] = useState(false);

  async function handleLogout() {
    setBusy(true);
    try {
      await logout();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="app-header">
        <span className="brand">FoodVerse AI</span>
        <nav aria-label="Main">
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/preferences">Preferences</NavLink>
        </nav>
        <div className="user-box">
          <span>{state.user?.display_name}</span>
          <button type="button" className="secondary" onClick={handleLogout} disabled={busy}>
            Sign out
          </button>
        </div>
      </header>
      <main className="container">
        <Outlet />
      </main>
    </>
  );
}
