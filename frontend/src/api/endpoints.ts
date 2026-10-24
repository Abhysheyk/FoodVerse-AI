import { request, requestBlob, setAccessToken } from "./client";
import type {
  AIStatus,
  AuthResponse,
  DashboardSummary,
  HistoryItem,
  MediaItem,
  ModuleInfo,
  ModuleKey,
  Page,
  PreferenceOptions,
  Preferences,
  PreferencesInput,
  User,
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

export const getDashboardSummary = () => request<DashboardSummary>("/dashboard/summary");
export const getModules = () => request<ModuleInfo[]>("/modules");

export const updateProfile = (displayName: string) =>
  request<User>("/users/me", { method: "PATCH", body: { display_name: displayName } });
export const changePassword = (currentPassword: string, newPassword: string) =>
  request<void>("/users/me/password", {
    method: "POST",
    body: { current_password: currentPassword, new_password: newPassword },
  });

export function listMedia(page: number, pageSize = 12) {
  return request<Page<MediaItem>>(`/media?page=${page}&page_size=${pageSize}`);
}
export function uploadMedia(file: File) {
  const form = new FormData();
  form.append("file", file);
  return request<MediaItem>("/media", { method: "POST", body: form });
}
export const deleteMedia = (id: string) => request<void>(`/media/${id}`, { method: "DELETE" });
export const getMediaBlob = (id: string, download = false) =>
  requestBlob(`/media/${id}/content${download ? "?download=true" : ""}`);

export function listHistory(page: number, module: ModuleKey | null, pageSize = 10) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (module) params.set("module", module);
  return request<Page<HistoryItem>>(`/history?${params.toString()}`);
}
export const deleteHistory = (id: string) => request<void>(`/history/${id}`, { method: "DELETE" });
