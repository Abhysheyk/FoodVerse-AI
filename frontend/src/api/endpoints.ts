import { request, requestBlob, requestUpload, setAccessToken } from "./client";
import type {
  AIStatus,
  AuthResponse,
  Calculation,
  DashboardSummary,
  FoodCapabilities,
  FreshnessCapabilities,
  FreshnessDetail,
  FreshnessLabel,
  FreshnessRequest,
  FreshnessSummary,
  FoodItemPayload,
  HistoryItem,
  MealCategory,
  MealDetail,
  MealSummary,
  MealWriteBody,
  MediaItem,
  ModuleInfo,
  ModuleKey,
  Page,
  PreferenceOptions,
  NutritionSearchResponse,
  Preferences,
  PreferencesInput,
  ScanResponse,
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

// ---- Food recognition & nutrition ----
export const uploadPhotoWithProgress = (file: File, onProgress: (fraction: number) => void, signal?: AbortSignal) => {
  const form = new FormData();
  form.append("file", file);
  return requestUpload<MediaItem>("/media", form, onProgress, signal);
};
export const getFoodCapabilities = () => request<FoodCapabilities>("/food/capabilities");
export const scanPhoto = (mediaId: string, signal?: AbortSignal) =>
  request<ScanResponse>("/food/scan", { method: "POST", body: { media_id: mediaId }, signal });
export const searchFoods = (query: string, signal?: AbortSignal) =>
  request<NutritionSearchResponse>(`/nutrition/search?q=${encodeURIComponent(query)}`, { signal });
export const calculateMeal = (items: FoodItemPayload[], scanRef: string | null, mealId?: string) =>
  request<Calculation>("/food/calculate", {
    method: "POST",
    body: { items, scan_ref: scanRef, ...(mealId ? { meal_id: mealId } : {}) },
  });

export function listMeals(page: number, category: MealCategory | null, pageSize = 10) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (category) params.set("category", category);
  return request<Page<MealSummary>>(`/meals?${params.toString()}`);
}
export const getMeal = (id: string) => request<MealDetail>(`/meals/${id}`);
export const createMeal = (body: MealWriteBody) => request<MealDetail>("/meals", { method: "POST", body });
export const updateMeal = (id: string, body: MealWriteBody) =>
  request<MealDetail>(`/meals/${id}`, { method: "PUT", body });
export const deleteMeal = (id: string) => request<void>(`/meals/${id}`, { method: "DELETE" });

// ---- Freshness assessment ----
export const getFreshnessCapabilities = () => request<FreshnessCapabilities>("/freshness/capabilities");
export const createFreshness = (body: FreshnessRequest, signal?: AbortSignal) =>
  request<FreshnessDetail>("/freshness/assessments", { method: "POST", body, signal });
export function listFreshness(page: number, label: FreshnessLabel | null, pageSize = 10) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (label) params.set("label", label);
  return request<Page<FreshnessSummary>>(`/freshness/assessments?${params.toString()}`);
}
export const getFreshness = (id: string) => request<FreshnessDetail>(`/freshness/assessments/${id}`);
export const deleteFreshness = (id: string) =>
  request<void>(`/freshness/assessments/${id}`, { method: "DELETE" });
