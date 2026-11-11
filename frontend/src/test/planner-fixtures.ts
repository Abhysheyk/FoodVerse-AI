import type { Handler } from "./helpers";
import { json } from "./helpers";

export const USER = {
  id: "u1", email: "asha@example.com", display_name: "Asha", created_at: "2026-10-24T00:00:00Z",
};

export const CAPS = {
  text_provider_configured: true,
  text_provider: "openai_compatible",
  text_provider_external: true,
  text_model: "test-model",
  message: null,
  nutrition_sources_configured: true,
};

export const CAPS_OFFLINE = {
  ...CAPS,
  text_provider_configured: false,
  text_provider: null,
  text_model: null,
  message: "Meal plan generation is not configured. Create a blank plan and edit it manually.",
};

const day = (i: number) => ({
  day_date: `2026-11-${String(2 + i).padStart(2, "0")}`,
  meals: [
    {
      meal: "lunch", title: `Lunch ${i}`, servings: 1, cooking_minutes: 20,
      ingredients: [{ name: "rice", quantity: 100, unit: "g" }], notes: null,
    },
  ],
});

export const PLAN = {
  id: "plan1", title: "Test plan", week_start_date: "2026-11-02",
  source: "ai", status: "draft", revision: 1, day_count: 7, meal_count: 7,
  created_at: "2026-11-01T12:00:00Z", updated_at: "2026-11-01T12:00:00Z",
  notes: null,
  plan: { schema_version: 1, days: Array.from({ length: 7 }, (_, i) => day(i)), notes: null },
  model_meta: null, estimate: null, estimated_at: null,
};

export const BLANK = {
  ...PLAN, source: "manual", title: "Blank plan",
  plan: {
    schema_version: 1,
    days: Array.from({ length: 7 }, (_, i) => ({
      day_date: `2026-11-${String(2 + i).padStart(2, "0")}`,
      meals: [{
        meal: "breakfast", title: "", servings: 1, cooking_minutes: null,
        ingredients: [], notes: null,
      }],
    })),
    notes: null,
  },
};

export const GROCERY = {
  id: "gl1", title: "Groceries for Test plan", plan_id: "plan1", revision: 1,
  item_count: 1, checked_count: 0,
  created_at: "2026-11-01T12:00:00Z", updated_at: "2026-11-01T12:00:00Z",
  items: [
    { id: "gi1", name: "rice", quantity: 500, unit: "g", checked: false, position: 0, notes: null },
  ],
};

export const plannerRoutes = (over: Record<string, Handler> = {}): Record<string, Handler> => ({
  "POST /auth/refresh": () => json(200, {
    access_token: "access-1", token_type: "bearer", expires_in: 900, user: USER,
  }),
  "GET /meal-plans/capabilities": () => json(200, CAPS),
  "GET /meal-plans?page=1&page_size=10": () =>
    json(200, { items: [], total: 0, page: 1, page_size: 10, pages: 0 }),
  ...over,
});