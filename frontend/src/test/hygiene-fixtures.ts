import type { Handler } from "./helpers";
import { json } from "./helpers";
import { CAPS_READY, MEDIA } from "./food-fixtures";

export const HCAPS = {
  vision: CAPS_READY.vision,
  location_types: [
    { value: "restaurant_kitchen", label: "Restaurant kitchen" },
    { value: "home_kitchen", label: "Home kitchen" },
  ],
  statuses: [
    { value: "draft", label: "Draft" },
    { value: "in_review", label: "In review" },
    { value: "approved", label: "Approved" },
    { value: "rejected", label: "Rejected" },
  ],
  default_checklist: [
    { item_id: "handwashing", label: "Handwashing station stocked", checked: false, note: null },
    { item_id: "surfaces_clean", label: "Work surfaces clean", checked: false, note: null },
  ],
  max_photos: 8,
};

export const FINDING = {
  finding_id: "f-1",
  source: "model" as const,
  category: "surface_cleanliness" as const,
  category_label: "Surface cleanliness",
  severity: "medium" as const,
  severity_label: "Medium",
  description: "Greasy film on the cutting board",
  location: "left side",
  certainty: "clearly_visible" as const,
  certainty_label: "Clearly visible",
  evidence_media_id: "m1",
  evidence_description: null,
  user_note: null,
  suggested_action: "Clean and sanitize the affected surface before preparing food.",
};

export const DETAIL = {
  id: "i1",
  location_name: "Main kitchen",
  location_type: "restaurant_kitchen",
  location_type_label: "Restaurant kitchen",
  area: "Prep station",
  status: "draft" as const,
  status_label: "Draft",
  finding_count: 1,
  highest_severity: "medium" as const,
  photo_count: 1,
  revision: 1,
  reviewed_at: null,
  created_at: "2026-10-27T10:00:00Z",
  updated_at: "2026-10-27T10:00:00Z",
  media_ids: ["m1"],
  notes: null,
  review_notes: null,
  result: {
    schema_version: 1,
    location: { name: "Main kitchen", type: "restaurant_kitchen", type_label: "Restaurant kitchen", area: "Prep station" },
    checklist: HCAPS.default_checklist,
    findings: [FINDING],
    notes: null,
    disclosures: ["Photos cannot confirm absence of pathogens."],
    not_assessable: ["Pathogen presence cannot be established from a photo."],
    model_limitations: [],
    model_notes: null,
    withheld_text_count: 0,
    provider: { name: "ollama", model: "llava-test", external: false },
    analyzed_at: "2026-10-27T10:00:00Z",
    generated_at: "2026-10-27T10:00:00Z",
  },
};

export const LIST_PAGE = (items: unknown[] = [DETAIL]) => ({
  items, total: items.length, page: 1, page_size: 10, pages: items.length ? 1 : 0,
});

export const hygieneRoutes = (over: Record<string, Handler> = {}): Record<string, Handler> => ({
  "POST /auth/refresh": () => json(200, {
    access_token: "access-1", token_type: "bearer", expires_in: 900,
    user: { id: "u1", email: "asha@example.com", display_name: "Asha", created_at: "2026-10-24T00:00:00Z" },
  }),
  "GET /hygiene/capabilities": () => json(200, HCAPS),
  "GET /media/m1/content": () => new Response(new Uint8Array([1]), { headers: { "Content-Type": "image/png" } }),
  ...over,
});
void MEDIA;