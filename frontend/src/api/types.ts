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

// ---- Food recognition & nutrition (Phase 3) ----
export type MealCategory = "breakfast" | "lunch" | "dinner" | "snack";
export type SourceState = "ok" | "not_configured" | "unavailable" | "rate_limited" | "timeout";

export interface SourceStatus {
  source: string;
  label: string;
  status: SourceState;
  message: string | null;
}

export interface NutrientDefinition {
  key: string;
  label: string;
  unit: string;
  core: boolean;
}

export interface FoodCapabilities {
  vision: {
    configured: boolean;
    provider: string | null;
    model: string | null;
    external: boolean;
    message: string | null;
  };
  nutrition: {
    sources: SourceStatus[];
    nutrients: NutrientDefinition[];
    any_configured: boolean;
    local_reference_records: number;
  };
}

/** A trusted source record, frozen when the user picked it. Values are per 100 g. */
export interface FoodSnapshot {
  source: string;
  source_label: string;
  source_id: string;
  name: string;
  brand: string | null;
  data_type: string | null;
  per_100g: Record<string, number>;
  serving_grams: number | null;
  serving_label: string | null;
  attribution: string;
  url: string | null;
  notes: string[];
}

export interface FoodCandidate extends FoodSnapshot {
  food_ref: string;
}

export interface NutritionSearchResponse {
  query: string;
  results: FoodCandidate[];
  sources: SourceStatus[];
}

export interface ObservedFood {
  observed_id: number;
  name: string;
  description: string;
  ambiguous: boolean;
  alternatives: string[];
}

export interface ScanResponse {
  scan_ref: string;
  media_id: string;
  provider: { name: string; model: string; external: boolean };
  items: ObservedFood[];
  notes: string | null;
  uncertainty_note: string;
  generated_at: string;
}

export type WeightUnit = "g" | "kg" | "oz" | "lb";
export type PortionInput =
  | { kind: "weight"; amount: number; unit: WeightUnit }
  | { kind: "range"; min_amount: number; max_amount: number; unit: WeightUnit }
  | { kind: "servings"; count: number };

export interface FoodItemPayload {
  item_id?: string;
  observed_id?: number;
  name: string;
  food_ref?: string;
  clear_food?: boolean;
  portion?: PortionInput;
}

export interface ItemCalculation {
  item_id: string;
  name: string;
  origin: "model" | "model_edited" | "user_added";
  observed_name: string | null;
  food: FoodSnapshot | null;
  portion_input: PortionInput | null;
  portion: { description: string; grams_low: number; grams_high: number; uncertain: boolean } | null;
  nutrients: Record<string, { low: number; high: number; unit: string }>;
  not_reported: string[];
  warnings: string[];
}

export interface TotalNutrient {
  key: string;
  label: string;
  unit: string;
  low: number | null;
  high: number | null;
  complete: boolean;
  contributing_items: number;
  missing_items: string[];
}

export interface Calculation {
  items: ItemCalculation[];
  totals: Record<string, TotalNutrient>;
  warnings: string[];
  unit_basis: string;
  method: string;
  disclaimer: string;
}

export interface MealAudit extends Calculation {
  schema_version: number;
  model_observations: {
    provider: { name: string; model: string; external: boolean };
    media_id: string;
    items: ObservedFood[];
    notes: string | null;
    generated_at: string;
    uncertainty_note: string;
  } | null;
}

export interface MealSummary {
  id: string;
  title: string;
  items_label: string;
  category: MealCategory;
  eaten_at: string;
  item_count: number;
  calories: { low: number | null; high: number | null; complete: boolean };
  media_id: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface MealDetail extends MealSummary {
  notes: string | null;
  result: MealAudit;
}

export interface MealWriteBody {
  items: FoodItemPayload[];
  eaten_at: string;
  category: MealCategory;
  notes: string | null;
  media_id?: string | null;
  scan_ref?: string | null;
  expected_revision?: number;
}

// ---- Freshness / spoilage-sign assessment (Phase 4) ----
export type FreshnessLabel = "visible_concern_observed" | "no_obvious_visible_concern" | "inconclusive";
export type AdviceLevel = "discard_recommended" | "use_caution" | "general_caution";

export interface Choice {
  value: string;
  label: string;
}

export interface FreshnessCapabilities {
  vision: FoodCapabilities["vision"];
  categories: Choice[];
  storage_conditions: Choice[];
  packaging: Choice[];
  classifier_enabled: boolean;
  verdict_notice: string;
}

export interface FreshnessRequest {
  media_id: string | null;
  analyze_image: boolean;
  food_name: string;
  food_category: string;
  storage_condition: string;
  packaging: string;
  storage_duration: { amount: number; unit: "hours" | "days" } | null;
  purchased_on: string | null;
  use_by_date: string | null;
  best_before_date: string | null;
  assessed_on: string;
  notes: string | null;
}

export interface FreshnessObservation {
  feature: string;
  feature_label: string;
  description: string;
  location: string;
  severity: "slight" | "moderate" | "marked";
  certainty: "clearly_visible" | "possibly_visible";
}

export interface Reason {
  code: string;
  text: string;
}

export interface FreshnessAudit {
  schema_version: number;
  food: { name: string; category: string; category_label: string };
  inputs: {
    storage_condition: string;
    packaging: string;
    storage_hours: number | null;
    purchased_on: string | null;
    use_by_date: string | null;
    best_before_date: string | null;
    assessed_on: string;
    notes: string | null;
  };
  findings: {
    analysed: boolean;
    image_quality: "clear" | "limited" | "unusable" | null;
    food_visible: boolean | null;
    matches_confirmed_food: "yes" | "no" | "unsure" | null;
    observations: FreshnessObservation[];
    limitations: string[];
    notes: string | null;
    withheld_text_count: number;
  };
  assessment: { label: FreshnessLabel; label_text: string; inconclusive_reasons: Reason[] };
  advice: {
    level: AdviceLevel;
    headline: string;
    reasons: Reason[];
    steps: string[];
    category_cautions: string[];
    general_notes: string[];
    retake_tips: string[];
    sources: { name: string; url: string }[];
  };
  provider: { name: string; model: string; external: boolean } | null;
  classifier_result: null;
  verdict_notice: string;
  generated_at: string;
}

export interface FreshnessSummary {
  id: string;
  food_name: string;
  food_category: string;
  category_label: string;
  label: FreshnessLabel;
  label_text: string;
  advice_level: AdviceLevel;
  image_analysed: boolean;
  media_id: string | null;
  created_at: string;
}

export interface FreshnessDetail extends FreshnessSummary {
  result: FreshnessAudit;
}

// ---- Hygiene inspections (Phase 5) ----
export type HygieneStatus = "draft" | "in_review" | "approved" | "rejected";
export type HygieneSeverity = "low" | "medium" | "high";
export type HygieneCertainty = "clearly_visible" | "possibly_visible";
export type HygieneCategory =
  | "surface_cleanliness"
  | "uncovered_food"
  | "raw_ready_to_eat_separation"
  | "waste_management"
  | "tool_cleanliness"
  | "other_visible_concern";
export type HygieneLocationType =
  | "restaurant_kitchen" | "cafe" | "food_truck" | "home_kitchen" | "institutional" | "other";

export interface HygieneChoice { value: string; label: string }
export interface ChecklistItem { item_id: string; label: string; checked: boolean; note: string | null }
export interface HygieneCapabilities {
  vision: FoodCapabilities["vision"];
  location_types: HygieneChoice[];
  statuses: HygieneChoice[];
  default_checklist: ChecklistItem[];
  max_photos: number;
}

export interface HygieneFinding {
  finding_id: string;
  source: "model" | "user" | "user_edited";
  category: HygieneCategory;
  category_label: string;
  severity: HygieneSeverity;
  severity_label: string;
  description: string;
  location: string;
  certainty: HygieneCertainty;
  certainty_label: string;
  evidence_media_id: string | null;
  evidence_description: string | null;
  user_note: string | null;
  suggested_action: string;
}

export interface HygieneFindingInput {
  finding_id?: string;
  source?: "model" | "user";
  category: HygieneCategory;
  severity: HygieneSeverity;
  description: string;
  location: string;
  certainty: HygieneCertainty;
  evidence_media_id?: string | null;
  evidence_description?: string | null;
  user_note?: string | null;
}

export interface HygieneAudit {
  schema_version: number;
  location: { name: string; type: string; type_label: string; area: string | null };
  checklist: ChecklistItem[];
  findings: HygieneFinding[];
  notes: string | null;
  disclosures: string[];
  not_assessable: string[];
  model_limitations: string[];
  model_notes: string | null;
  withheld_text_count: number;
  provider: { name: string; model: string; external: boolean } | null;
  analyzed_at: string | null;
  generated_at: string;
}

export interface HygieneSummary {
  id: string;
  location_name: string;
  location_type: string;
  location_type_label: string;
  area: string | null;
  status: HygieneStatus;
  status_label: string;
  finding_count: number;
  highest_severity: HygieneSeverity | null;
  photo_count: number;
  revision: number;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface HygieneDetail extends HygieneSummary {
  media_ids: string[];
  notes: string | null;
  review_notes: string | null;
  result: HygieneAudit;
}

export interface HygieneCreateBody {
  location_name: string;
  location_type: HygieneLocationType;
  area: string | null;
  media_ids: string[];
  notes: string | null;
}

export interface HygieneUpdateBody {
  expected_revision?: number;
  location_name?: string;
  location_type?: HygieneLocationType;
  area?: string | null;
  media_ids?: string[];
  notes?: string | null;
  checklist?: ChecklistItem[];
  findings?: HygieneFindingInput[];
}

// ---- Cooking assistant (Phase 6) ----
export interface TextProviderInfo { name: string; model: string; external: boolean }

export interface RecipeIngredient {
  name: string; quantity: number | null; unit: string | null; note: string | null; optional: boolean;
}
export interface RecipeStep { number: number; instruction: string; duration_minutes: number | null }
export interface RecipeSubstitution { ingredient: string; alternative: string; note: string | null }

export interface RecipeNutrition {
  whole_recipe: Calculation;
  per_serving: Record<string, TotalNutrient>;
  basis: string; servings: number; linked_items: number; note: string;
}

export interface Recipe {
  id: string; title: string; description: string | null; servings: number;
  prep_minutes: number | null; cook_minutes: number | null; total_minutes: number | null;
  equipment: string[]; ingredients: RecipeIngredient[]; steps: RecipeStep[];
  substitutions: RecipeSubstitution[]; dietary_tags: string[]; allergen_warnings: string[];
  safety_notes: string[]; beginner_notes: string[]; tips: string[];
  status: "suggested" | "saved"; favorite: boolean; revision: number;
  provider: TextProviderInfo | null; nutrition: RecipeNutrition | null;
  generated_at: string | null; created_at: string; updated_at: string;
  context_note: string; allergy_note: string;
}

export interface RecipeSummary {
  id: string; title: string; servings: number; total_minutes: number | null;
  status: "suggested" | "saved"; favorite: boolean; dietary_tags: string[];
  ingredient_count: number; updated_at: string;
}

export interface ChatMessage {
  id: string; role: "user" | "assistant"; content: string;
  recipe_id: string | null; warnings: string[]; created_at: string;
}

export interface ChatResponse {
  conversation_id: string;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
  recipe: Recipe | null;
  provider: TextProviderInfo;
}

export interface ConversationSummary {
  id: string; title: string; message_count: number;
  created_at: string; updated_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessage[]; recipes: RecipeSummary[];
}

export interface CookingCapabilities {
  text: {
    configured: boolean; provider: string | null; model: string | null;
    external: boolean; message: string | null;
  };
  diets: { value: string; label: string }[];
  max_servings: number; context_messages: number;
  allergy_note: string; context_note: string;
}

export interface RecipeWriteBody {
  title: string; description: string | null; servings: number;
  prep_minutes: number | null; cook_minutes: number | null;
  equipment: string[]; ingredients: RecipeIngredient[];
  steps: { instruction: string; duration_minutes: number | null }[];
  substitutions: RecipeSubstitution[];
  dietary_tags: string[]; tips: string[]; beginner_notes: string[]; safety_notes: string[];
  expected_revision?: number;
}
