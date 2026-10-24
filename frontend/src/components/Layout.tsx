import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ClockIcon, GridIcon, HomeIcon, ImageIcon, LogoMark, SettingsIcon } from "./icons";

const NAV = [
  { to: "/", label: "Dashboard", icon: <HomeIcon />, end: true },
  { to: "/modules", label: "Modules", icon: <GridIcon />, end: false },
  { to: "/history", label: "History", icon: <ClockIcon />, end: false },
  { to: "/media", label: "Media", icon: <ImageIcon />, end: false },
  { to: "/settings", label: "Settings", icon: <SettingsIcon />, end: false },
];

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
    <div className="shell">
      <a className="skip-link" href="#main">Skip to main content</a>
      <header className="shell-brand">
        <LogoMark />
        <span className="brand-name">FoodVerse <span>AI</span></span>
      </header>
      <nav className="shell-nav" aria-label="Main">
        {NAV.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end}>
            {item.icon}
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="shell-user">
        <span className="user-name" title={state.user?.email}>{state.user?.display_name}</span>
        <button type="button" className="secondary small" onClick={handleLogout} disabled={busy}>
          Sign out
        </button>
      </div>
      <main id="main" className="shell-main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
