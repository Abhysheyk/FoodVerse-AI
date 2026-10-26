import type { Handler } from "./helpers";
import { json } from "./helpers";

export const CAPS_READY = {
  vision: { configured: true, provider: "ollama", model: "llava-test", external: false, message: null },
  nutrition: {
    sources: [{ source: "usda_fdc", label: "USDA FoodData Central", status: "ok", message: null }],
    nutrients: [],
    any_configured: true,
    local_reference_records: 0,
  },
};

export const CAPS_NO_VISION = {
  ...CAPS_READY,
  vision: { configured: false, provider: null, model: null, external: false, message: "OLLAMA_ENABLED is not set." },
};

export const SCAN = {
  scan_ref: "scan-ref-1",
  media_id: "m1",
  provider: { name: "ollama", model: "llava-test", external: false },
  items: [
    { observed_id: 0, name: "Apple", description: "A red apple", ambiguous: true, alternatives: ["Pear"] },
    { observed_id: 1, name: "Rice", description: "", ambiguous: false, alternatives: [] },
  ],
  notes: null,
  uncertainty_note: "Item names come from an image model and may be wrong. Please check every item.",
  generated_at: "2026-10-25T10:00:00Z",
};

export const MEDIA = {
  id: "m1", kind: "image", content_type: "image/png", display_name: "plate.png", size_bytes: 1000,
  width: 64, height: 48, duration_seconds: null, created_at: "2026-10-25T10:00:00Z",
};

export const FOOD = {
  source: "usda_fdc", source_label: "USDA FoodData Central", source_id: "171688",
  name: "Apples, raw, with skin", brand: null, data_type: "SR Legacy",
  per_100g: { energy_kcal: 52, protein_g: 0.26, carbs_g: 13.8, fat_g: 0.17 },
  serving_grams: null, serving_label: null,
  attribution: "USDA FoodData Central (U.S. Department of Agriculture)", url: null, notes: [],
};

export const SEARCH = {
  query: "apple",
  results: [{ ...FOOD, food_ref: "food-ref-1" }],
  sources: [{ source: "usda_fdc", label: "USDA FoodData Central", status: "ok", message: null }],
};

const total = (key: string, label: string, unit: string, low: number | null, high: number | null, complete = true, missing: string[] = []) => ({
  key, label, unit, low, high, complete, contributing_items: low === null ? 0 : 1, missing_items: missing,
});

export const CALC = {
  items: [
    {
      item_id: "i1", name: "Apple", origin: "model", observed_name: "Apple", food: FOOD,
      portion_input: { kind: "weight", amount: 150, unit: "g" },
      portion: { description: "150 g", grams_low: 150, grams_high: 150, uncertain: false },
      nutrients: {
        energy_kcal: { low: 78, high: 78, unit: "kcal" }, protein_g: { low: 0.39, high: 0.39, unit: "g" },
        carbs_g: { low: 20.7, high: 20.7, unit: "g" }, // fat not reported by the source
      },
      not_reported: ["fat_g", "fiber_g"], warnings: ["partial_nutrients"],
    },
    {
      item_id: "i2", name: "Rice", origin: "model", observed_name: "Rice", food: null,
      portion_input: null, portion: null, nutrients: {}, not_reported: [],
      warnings: ["no_nutrition_data", "portion_missing"],
    },
  ],
  totals: {
    energy_kcal: total("energy_kcal", "Calories", "kcal", 78, 78, false, ["Rice"]),
    protein_g: total("protein_g", "Protein", "g", 0.39, 0.39, false, ["Rice"]),
    carbs_g: total("carbs_g", "Carbohydrates", "g", 20.7, 20.7, false, ["Rice"]),
    fat_g: total("fat_g", "Fat", "g", null, null, false, ["Apple", "Rice"]),
    fiber_g: total("fiber_g", "Fibre", "g", null, null, false, ["Apple", "Rice"]),
  },
  warnings: ["incomplete_totals"],
  unit_basis: "per 100 g, as published by each source",
  method: "nutrient per 100 g x grams eaten / 100, summed over items",
  disclaimer: "Estimates only. Not medical or dietary advice.",
};

export const MEAL = {
  id: "meal1", title: "Lunch: Apple, Rice", items_label: "Apple, Rice", category: "lunch",
  eaten_at: "2026-10-25T07:30:00Z", item_count: 2,
  calories: { low: 78, high: 78, complete: false },
  media_id: "m1", revision: 1, created_at: "2026-10-25T08:00:00Z", updated_at: "2026-10-25T08:00:00Z",
  notes: "with tea",
  result: {
    ...CALC, schema_version: 1,
    model_observations: {
      provider: SCAN.provider, media_id: "m1", items: SCAN.items, notes: null,
      generated_at: SCAN.generated_at, uncertainty_note: SCAN.uncertainty_note,
    },
  },
};

export const mealPage = (items: unknown[] = [MEAL], over: object = {}) => ({
  items, total: items.length, page: 1, page_size: 10, pages: items.length ? 1 : 0, ...over,
});

/** Routes shared by food tests. */
export const foodRoutes = (over: Record<string, Handler> = {}): Record<string, Handler> => ({
  "POST /auth/refresh": () => json(200, {
    access_token: "access-1", token_type: "bearer", expires_in: 900,
    user: { id: "u1", email: "asha@example.com", display_name: "Asha", created_at: "2026-10-24T00:00:00Z" },
  }),
  "GET /food/capabilities": () => json(200, CAPS_READY),
  ...over,
});
