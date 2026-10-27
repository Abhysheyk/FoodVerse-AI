import type { Handler } from "./helpers";
import { json } from "./helpers";
import { CAPS_READY } from "./food-fixtures";

const choices = (xs: string[]) => xs.map((v) => ({ value: v, label: v[0].toUpperCase() + v.slice(1).replace(/_/g, " ") }));
export const NOTICE = "This describes what is visible in one image. It is not a verdict that food is safe or unsafe.";

export const FCAPS = {
  vision: CAPS_READY.vision,
  categories: [{ value: "fruit", label: "Fruit" }, { value: "meat_poultry", label: "Meat and poultry" }],
  storage_conditions: choices(["unknown", "fridge", "room_temperature"]),
  packaging: choices(["unknown", "sealed", "opened"]),
  classifier_enabled: false,
  verdict_notice: NOTICE,
};
export const FCAPS_NO_VISION = {
  ...FCAPS,
  vision: { configured: false, provider: null, model: null, external: false, message: "OLLAMA_ENABLED is not set." },
};

export const SUMMARY = {
  id: "f1", food_name: "Strawberries", food_category: "fruit", category_label: "Fruit",
  label: "visible_concern_observed", label_text: "Visible concern observed",
  advice_level: "use_caution", image_analysed: true, media_id: "m1", created_at: "2026-10-27T05:00:00Z",
};

export const audit = (over: Record<string, unknown> = {}, label = "visible_concern_observed") => ({
  schema_version: 1,
  food: { name: "Strawberries", category: "fruit", category_label: "Fruit" },
  inputs: {
    storage_condition: "fridge", packaging: "opened", storage_hours: 72, purchased_on: null,
    use_by_date: null, best_before_date: null, assessed_on: "2026-10-27", notes: null,
  },
  findings: {
    analysed: true, image_quality: "clear", food_visible: true, matches_confirmed_food: "yes",
    observations: [{
      feature: "mold_like_growth", feature_label: "Mold-like growth", description: "Grey fuzzy patch",
      location: "top left", severity: "moderate", certainty: "clearly_visible",
    }],
    limitations: ["Only one side is visible"], notes: null, withheld_text_count: 0,
  },
  assessment: { label, label_text: "Visible concern observed", inconclusive_reasons: [] },
  advice: {
    level: "discard_recommended", headline: "Discarding is recommended.",
    reasons: [{ code: "mold", text: "Mold-like growth was reported." }],
    steps: ["Do not taste it to check."], category_cautions: ["Soft fruit can hide mold."],
    general_notes: ["Microbes cannot always be seen."], retake_tips: [],
    sources: [{ name: "FoodSafety.gov", url: "https://www.foodsafety.gov" }],
  },
  provider: { name: "ollama", model: "llava-test", external: false },
  classifier_result: null, verdict_notice: NOTICE, generated_at: "2026-10-27T05:00:00Z",
  ...over,
});

export const DETAIL = { ...SUMMARY, result: audit() };
export const fpage = (items: unknown[] = [SUMMARY]) => ({
  items, total: items.length, page: 1, page_size: 10, pages: items.length ? 1 : 0,
});

export const freshRoutes = (over: Record<string, Handler> = {}): Record<string, Handler> => ({
  "POST /auth/refresh": () => json(200, {
    access_token: "access-1", token_type: "bearer", expires_in: 900,
    user: { id: "u1", email: "asha@example.com", display_name: "Asha", created_at: "2026-10-24T00:00:00Z" },
  }),
  "GET /freshness/capabilities": () => json(200, FCAPS),
  ...over,
});
