import type { ReactNode } from "react";

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor"
      strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

export const HomeIcon = () => <Icon><path d="M3 11l9-8 9 8" /><path d="M5 10v10h14V10" /></Icon>;
export const GridIcon = () => <Icon><rect x="3" y="3" width="7" height="7" rx="1.5" /><rect x="14" y="3" width="7" height="7" rx="1.5" /><rect x="3" y="14" width="7" height="7" rx="1.5" /><rect x="14" y="14" width="7" height="7" rx="1.5" /></Icon>;
export const ClockIcon = () => <Icon><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></Icon>;
export const ImageIcon = () => <Icon><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="9" cy="10" r="1.6" /><path d="M21 16l-5-5-8 8" /></Icon>;
export const SettingsIcon = () => <Icon><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z" /></Icon>;
export const CameraIcon = () => <Icon><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></Icon>;
export const PlateIcon = () => <Icon><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="5" /></Icon>;

export function LogoMark() {
  return (
    <svg viewBox="0 0 32 32" width="32" height="32" aria-hidden="true" focusable="false">
      <rect width="32" height="32" rx="9" fill="var(--brand)" />
      <path d="M9 21c0-6 4-10 14-11-1 9-5 13-11 13-1.2 0-2-.5-3-2z" fill="var(--brand-fg)" />
      <path d="M9 24c2-5 5-8 9-10" stroke="var(--brand)" strokeWidth="1.6" strokeLinecap="round" fill="none" />
      <circle cx="23.5" cy="8.5" r="2.5" fill="var(--citrus)" />
    </svg>
  );
}
