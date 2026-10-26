# ADR 0003: Food recognition and nutrition analysis

Status: accepted (Phase 3)

## Principle
**The model identifies candidates; the user confirms them; trusted data supplies nutrient values;
deterministic code calculates totals.** No language or vision model ever produces, estimates or
adjusts a nutrition number, a portion weight or a confidence score.

## Flow
1. `POST /food/scan` sends one of the user's own stored photos to the configured vision provider.
   The prompt forbids weights, calories and guessing; output must match a JSON schema.
2. `parse_vision_output` validates the reply. Anything malformed (bad JSON, wrong shape, too many
   items, empty names) is **rejected, never repaired**, and the user gets a 502.
3. The response carries `scan_ref`, an HMAC-signed, user-bound, expiring token that holds what the
   model actually said. The browser cannot alter it, and it is what gets stored for the audit trail.
4. The user edits the list (rename, add, remove), searches `GET /nutrition/search`, and picks a
   match. Each candidate is returned with a signed `food_ref` (frozen source record, per 100 g).
5. `POST /food/calculate` accepts only `{name, observed_id?, food_ref?, portion}` per item. Client
   supplied nutrient numbers are rejected (`extra=forbid`); a tampered, expired or foreign
   `food_ref`/`scan_ref` returns 422 `invalid_reference`.
6. `POST /meals` repeats the calculation server-side and stores the complete audit JSON
   (items, source records with attribution, portions, per-item and total values, warnings, model
   observations) as an `analysis_records` row plus a `meal_logs` row that shares its primary key,
   so meals appear in History and deleting either deletes both.

## Vision providers
Exactly one, chosen by configuration, with **no fallback**: Ollama (`OLLAMA_ENABLED`,
`OLLAMA_VISION_MODEL`) or an OpenAI-compatible `/chat/completions` server (`VISION_PROVIDER=
openai_compatible`, refused unless `ALLOW_EXTERNAL_AI_PROVIDERS=true`). The UI discloses when a
photo would leave the machine (`external`). Nothing is downloaded automatically.

## Nutrition sources (per 100 g, all optional)
- **USDA FoodData Central** (`USDA_FDC_API_KEY`): Foundation + SR Legacy only, because those are
  published per 100 g. The key stays server-side; the httpx logger is pinned to WARNING so the
  key in the query string is never logged.
- **Open Food Facts** (`OPEN_FOOD_FACTS_ENABLED=true`): packaged foods and barcode lookup. kJ-only
  energy is converted (1 kcal = 4.184 kJ) and the conversion is noted; sodium g -> mg.
- **Local reference table** (`reference_foods`): empty by default. Operators import a CSV they
  are licensed to use (`python -m app.nutrition.import_reference`), which requires dataset,
  version, citation and licence note for every row. An empty cell means *not reported*, not 0.
  No IFCT values are bundled or typed from memory.

A nutrient a source does not supply is absent everywhere (never defaulted to 0). Values outside
plausible bounds are treated as malformed and dropped. Each source reports a status
(`ok | not_configured | unavailable | rate_limited | timeout`), so partial outages are visible.

## Calculation (`app/domain/nutrition_calc.py`)
`Decimal` arithmetic: `nutrient_per_100g x grams / 100`, rounded half-up to 2 dp once at output.
Units: g, kg, oz, lb. Volumes (cup, ml) are **rejected** because they depend on density. A range
portion gives low-high and is flagged as an estimate; "servings" are accepted only when the
source states a serving weight in grams. Totals sum only items that reported the nutrient and
state `complete=false` plus the missing item names otherwise.

## Limits and abuse controls
Per-user in-process sliding windows (scan 6/min, search 30/min); a size cap on images sent to the
model; item caps (15 detected, 30 per meal); 5000 g per item. Limits reset on restart and are not
shared between workers (a shared store is planned for Phase 9).

## Consequences
- Accuracy depends on the chosen vision model and on the user's portion entries; the UI says so.
- Saved meals keep the source record they were calculated from, so later changes upstream do not
  silently rewrite history; editing a meal can re-pick a source.
- Barcode lookup exists in the API but has no UI yet.
