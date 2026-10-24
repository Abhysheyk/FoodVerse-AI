import type { ReactNode } from "react";
import { AuthProvider } from "../auth/AuthContext";
import { ToastProvider } from "./Toast";

/** Everything the app needs apart from the router (shared by main.tsx and the tests). */
export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ToastProvider>
      <AuthProvider>{children}</AuthProvider>
    </ToastProvider>
  );
}
