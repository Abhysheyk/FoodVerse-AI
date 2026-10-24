export interface User {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export type UnitSystem = "metric" | "imperial";

export interface Preferences {
  unit_system: UnitSystem;
  dietary_preferences: string[];
  allergies: string[];
  updated_at: string;
}

export interface PreferencesInput {
  unit_system: UnitSystem;
  dietary_preferences: string[];
  allergies: string[];
}

export interface PreferenceOptions {
  unit_systems: UnitSystem[];
  dietary_preferences: string[];
  common_allergens: string[];
}

export interface ModelStatus {
  name: string | null;
  configured: boolean;
  installed: boolean | null;
}

export interface AIStatus {
  ollama: {
    enabled: boolean;
    base_url: string;
    reachable: boolean | null;
    text_model: ModelStatus;
    vision_model: ModelStatus;
    error: string | null;
  };
  external_providers_allowed: boolean;
  fallback_policy: "none";
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export type ModuleKey =
  | "food_recognition"
  | "freshness"
  | "hygiene"
  | "cooking"
  | "meal_planning";

export interface ModuleInfo {
  key: ModuleKey;
  title: string;
  description: string;
  available: boolean;
}

export interface MediaItem {
  id: string;
  kind: "image" | "video" | "audio";
  content_type: string;
  display_name: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  created_at: string;
}

export type AnalysisStatus = "pending" | "completed" | "failed";

export interface HistoryItem {
  id: string;
  module: ModuleKey;
  status: AnalysisStatus;
  title: string;
  summary: string | null;
  media_id: string | null;
  created_at: string;
}

export interface DashboardSummary {
  media: { count: number; total_bytes: number; quota_bytes: number; max_upload_bytes: number };
  history: { total: number; by_module: Partial<Record<ModuleKey, number>> };
  recent: HistoryItem[];
}
