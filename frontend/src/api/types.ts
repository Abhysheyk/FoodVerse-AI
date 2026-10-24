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
