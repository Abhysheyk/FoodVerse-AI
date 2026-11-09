import { request, requestBlob, requestUpload, setAccessToken, requestText} from "./client";
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
  HygieneCapabilities,
  HygieneCreateBody,
  HygieneDetail,
  HygieneLocationType,
  HygieneStatus,
  HygieneSummary,
  HygieneUpdateBody,
  ChatResponse,
  CookingCapabilities,
  ConversationDetail,
  Recipe,
  RecipeSummary,
  RecipeWriteBody,
  ConversationSummary

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

// ---- Hygiene ----

export const getHygieneCapabilities = () => request<HygieneCapabilities>("/hygiene/capabilities");

export function listHygieneInspections(
  page: number, status: HygieneStatus | null, locationType: HygieneLocationType | null, pageSize = 10,
) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (status) params.set("status", status);
  if (locationType) params.set("location_type", locationType);
  return request<Page<HygieneSummary>>(`/hygiene/inspections?${params.toString()}`);
}
export const getHygieneInspection = (id: string) => request<HygieneDetail>(`/hygiene/inspections/${id}`);
export const createHygieneInspection = (body: HygieneCreateBody) =>
  request<HygieneDetail>("/hygiene/inspections", { method: "POST", body });
export const updateHygieneInspection = (id: string, body: HygieneUpdateBody) =>
  request<HygieneDetail>(`/hygiene/inspections/${id}`, { method: "PUT", body });
export const analyzeHygieneInspection = (id: string, signal?: AbortSignal) =>
  request<HygieneDetail>(`/hygiene/inspections/${id}/analyze`, { method: "POST", signal });
export const submitHygieneInspection = (id: string) =>
  request<HygieneDetail>(`/hygiene/inspections/${id}/submit`, { method: "POST" });
export const approveHygieneInspection = (id: string, reviewNotes: string | null) =>
  request<HygieneDetail>(`/hygiene/inspections/${id}/approve`, {
    method: "POST", body: { review_notes: reviewNotes },
  });
export const rejectHygieneInspection = (id: string, reviewNotes: string) =>
  request<HygieneDetail>(`/hygiene/inspections/${id}/reject`, {
    method: "POST", body: { review_notes: reviewNotes },
  });
export const deleteHygieneInspection = (id: string) =>
  request<void>(`/hygiene/inspections/${id}`, { method: "DELETE" });
export const fetchHygieneReportHtml = (id: string) =>
  requestText(`/hygiene/inspections/${id}/report`);

// ---- Cooking assistant ----
export const getCookingCapabilities = () => request<CookingCapabilities>("/cooking/capabilities");

export const sendChat = (message: string, conversationId: string | null, signal?: AbortSignal) =>
  request<ChatResponse>("/cooking/chat", {
    method: "POST",
    body: { message, conversation_id: conversationId },
    signal,
  });

export function listConversations(page: number, pageSize = 20) {
  return request<Page<ConversationSummary>>(`/cooking/conversations?page=${page}&page_size=${pageSize}`);
}
export const getConversation = (id: string) =>
  request<ConversationDetail>(`/cooking/conversations/${id}`);
export const deleteConversation = (id: string) =>
  request<void>(`/cooking/conversations/${id}`, { method: "DELETE" });

export const generateRecipe = (
  mode: "from_ingredients" | "free",
  ingredients: string[],
  servings: number,
  signal?: AbortSignal,
) => request<Recipe>("/cooking/recipes/generate", {
  method: "POST",
  body: { mode, ingredients, servings },
  signal,
});

export function listRecipes(page: number, q: string | null, favorite: boolean | null, pageSize = 10) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (q) params.set("q", q);
  if (favorite !== null) params.set("favorite", String(favorite));
  return request<Page<RecipeSummary>>(`/cooking/recipes?${params.toString()}`);
}
export const getRecipe = (id: string, servings?: number) =>
  request<Recipe>(`/cooking/recipes/${id}${servings ? `?servings=${servings}` : ""}`);
export const saveRecipe = (id: string) =>
  request<Recipe>(`/cooking/recipes/${id}/save`, { method: "POST" });
export const favoriteRecipe = (id: string, favorite: boolean) =>
  request<Recipe>(`/cooking/recipes/${id}/favorite`, { method: "POST", body: { favorite } });
export const updateRecipe = (id: string, body: RecipeWriteBody) =>
  request<Recipe>(`/cooking/recipes/${id}`, { method: "PUT", body });
export const deleteRecipe = (id: string) =>
  request<void>(`/cooking/recipes/${id}`, { method: "DELETE" });
export const attachRecipeNutrition = (
  id: string, links: { ingredient_index: number; food_ref: string; grams: number }[],
) => request<Recipe>(`/cooking/recipes/${id}/nutrition`, { method: "POST", body: { links } });
