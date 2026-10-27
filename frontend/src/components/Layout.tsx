import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { CameraIcon, LeafIcon, ClockIcon, GridIcon, HomeIcon, ImageIcon, LogoMark, PlateIcon, SettingsIcon } from "./icons";

// `extra` items are hidden from the phone tab bar (five fit) and reached from the dashboard instead.
const NAV = [
  { to: "/", label: "Dashboard", icon: <HomeIcon />, end: true, extra: false },
  { to: "/food", label: "Analyse", icon: <CameraIcon />, end: false, extra: false },
  { to: "/freshness", label: "Freshness", icon: <LeafIcon />, end: false, extra: false },
  { to: "/meals", label: "Meals", icon: <PlateIcon />, end: false, extra: false },
  { to: "/history", label: "History", icon: <ClockIcon />, end: false, extra: true },
  { to: "/modules", label: "Modules", icon: <GridIcon />, end: false, extra: true },
  { to: "/media", label: "Media", icon: <ImageIcon />, end: false, extra: true },
  { to: "/settings", label: "Settings", icon: <SettingsIcon />, end: false, extra: false },
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
          <NavLink key={item.to} to={item.to} end={item.end} className={item.extra ? "nav-extra" : undefined}>
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
