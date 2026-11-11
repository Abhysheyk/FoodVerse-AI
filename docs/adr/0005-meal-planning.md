# ADR 0005: Personalized meal planning

Status: accepted (Phase 7)

## Decision summary
- **Provider**: one configurable `TextProvider` (currently `openai_compatible`) targeting a free
  external API (Groq, OpenRouter, Together, Gemini's OpenAI endpoint). Enabling it requires
  `ALLOW_EXTERNAL_AI_PROVIDERS=true` because the prompt leaves the machine.
- **Model output**: only food names and quantities. The JSON schema has no fields for calories,
  macros, prices, confidence or safety claims; any volunteered such fields are ignored.
- **Hard constraints enforced in code**: allergies, excluded ingredients, dietary pattern. Violation
  → 422 with the offending ingredients listed; **nothing is saved**. Cooking-time and budget
  mismatches are soft warnings only.
- **Nutrition estimates**: computed by looking each ingredient up in the existing trusted nutrition
  sources. Only mass units (g, kg, oz, lb) are converted; volumes are NOT converted because they
  depend on density. Unmatched ingredients are reported as missing, never estimated.
- **Offline**: `TEXT_PROVIDER=none` disables generation but users can create a blank plan, edit it,
  and use the estimate endpoint (which only needs nutrition sources). No hardcoded example plan is
  ever saved as real data.
- **Persistence**: `meal_plans` (structure in `plan_json`, revisions for optimistic concurrency)
  plus `grocery_lists` / `grocery_items` (independent, so plans and lists have independent
  lifecycles). Snapshot-style: the plan stores what was generated; edits are explicit PUTs.
- **Grocery merging**: only within compatible unit families (mass/volume/count), only for the same
  ingredient name. Never merges different names or crosses families.
- **Tracking dashboard**: `consumed` = meals in the meal log; `planned` = meals in plans. The two
  are never added together. Chart only shown when ≥3 days have data.

## Consequences / limits
- Allergies are matched by keyword lists; "halal" and "kosher" are advisory only (a full ontology
  is out of scope). Every constraint list is user-visible in the UI, so the user can see what will
  be enforced.
- Provider latencies vary; the UI allows cancelling a slow request. A cancelled request that had
  already been saved server-side appears in the plan list (same behaviour as Phase 3/4).
- Rate limits are in-process (per-worker); a shared store remains a Phase 9 concern.
- Recipes are not implemented in this repository yet (they are scheduled after Phase 7 in the
  implementation plan). The plan format is forward-compatible: a later `recipe_id` per meal can be
  added without a schema change to the API (PlanMeal is `extra="ignore"`).