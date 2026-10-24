import { request, setAccessToken } from "./client";
import type {
  AIStatus,
  AuthResponse,
  PreferenceOptions,
  Preferences,
  PreferencesInput,
} from "./types";

export async function login(email: string, password: string): Promise<AuthResponse> {
  const data = await request<AuthResponse>("/auth/login", {
    method: "POST",
    body: { email, password },
    authenticated: false,
  });
  setAccessToken(data.access_token);
  return data;
}

export async function register(
  displayName: string,
  email: string,
  password: string,
): Promise<AuthResponse> {
  const data = await request<AuthResponse>("/auth/register", {
    method: "POST",
    body: { display_name: displayName, email, password },
    authenticated: false,
  });
  setAccessToken(data.access_token);
  return data;
}

export async function logout(): Promise<void> {
  try {
    await request<void>("/auth/logout", { method: "POST", authenticated: false });
  } finally {
    setAccessToken(null);
  }
}

export const getPreferences = () => request<Preferences>("/users/me/preferences");
export const updatePreferences = (body: PreferencesInput) =>
  request<Preferences>("/users/me/preferences", { method: "PUT", body });
export const getPreferenceOptions = () =>
  request<PreferenceOptions>("/meta/preference-options", { authenticated: false });
export const getAIStatus = () => request<AIStatus>("/ai/status");
