import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import * as api from "../api/endpoints";
import { refreshSession, setAccessToken, setSessionLostHandler } from "../api/client";
import type { User } from "../api/types";

type AuthState =
  | { status: "loading"; user: null }
  | { status: "anonymous"; user: null }
  | { status: "authenticated"; user: User };

interface AuthContextValue {
  state: AuthState;
  login: (email: string, password: string) => Promise<void>;
  register: (displayName: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Replace the signed-in user's details after a profile edit. */
  updateUser: (user: User) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading", user: null });

  useEffect(() => {
    let cancelled = false;
    setSessionLostHandler(() => setState({ status: "anonymous", user: null }));
    // Restore an existing session from the HttpOnly refresh cookie (no token is persisted).
    void refreshSession().then((result) => {
      if (cancelled) return;
      setState(
        result
          ? { status: "authenticated", user: result.user }
          : { status: "anonymous", user: null },
      );
    });
    return () => {
      cancelled = true;
      setSessionLostHandler(null);
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const data = await api.login(email, password);
    setState({ status: "authenticated", user: data.user });
  }, []);

  const register = useCallback(async (displayName: string, email: string, password: string) => {
    const data = await api.register(displayName, email, password);
    setState({ status: "authenticated", user: data.user });
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // The server could not be reached, so the refresh cookie may still be valid until it
      // expires. The user is still signed out locally below.
    } finally {
      setAccessToken(null);
      setState({ status: "anonymous", user: null });
    }
  }, []);

  const updateUser = useCallback((user: User) => setState({ status: "authenticated", user }), []);

  const value = useMemo(
    () => ({ state, login, register, logout, updateUser }),
    [state, login, register, logout, updateUser],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
