# ADR 0004: Freshness and spoilage-sign assessment

Status: accepted (Phase 4)

## Context
Users want to know whether food that looks off is still fine to eat. A photo cannot answer that:
microbes, toxins and many spoilage processes are invisible, and a vision model can be wrong or
swayed by text in the image. Telling a user "this is safe" would be the most harmful possible output.

## Decision
**The model reports evidence only; fixed code decides the label and the advice.**

1. **Model contract.** The vision provider is asked (same configurable provider as Phase 3, via
   `complete_json`) for: image quality, whether food is visible, whether it matches the food the
   user confirmed, and a list of visible observations (feature, description, location, severity,
   certainty), plus limitations and a short note. The schema is strict. Malformed output is a 502
   and nothing is saved. There is no score or percentage anywhere.
2. **Verdict filter.** Free text from the model containing safety-verdict language (safe, unsafe,
   edible, "ok to eat", percentages, "score") is replaced with a fixed placeholder and counted
   (`withheld_text_count`), which the UI discloses.
3. **Label (deterministic, `app/domain/freshness.py`).** `inconclusive` if there is no analysis,
   no food visible, an unusable image, or the image does not match the confirmed food;
   `visible concern observed` if any observation exists; `no obvious visible concern in this image`
   only for a clear, matching image with no observations. These describe one image; none means safe.
4. **Advice (deterministic, fixed reviewed text).** Levels `discard_recommended`, `use_caution`,
   `general_caution`. Discard is triggered by mold-like growth, any concern on high-risk food
   (meat/poultry, fish/seafood, dairy/eggs, cooked food), more than 2 h at room temperature for
   high-risk food, cooked food in the fridge over 96 h, or a passed use-by date on high-risk food.
   Every result carries the reminder that spoilage can be invisible. Sources are linked
   (foodsafety.gov, fsis.usda.gov). Rules are commonly published advice and differ by country.
5. **Offline mode.** `analyze_image=false` never contacts a model, so guidance works when the AI
   provider is down or unconfigured. The record states that the photo was not analysed.
6. **Persistence.** One `analysis_records` row (audit JSON, module `freshness`) plus a
   `freshness_assessments` row sharing its primary key. Owner-only access (404 otherwise),
   deletion cascades, history lists and filters by label.
7. **Classifier.** No trained freshness classifier is shipped or configurable. Only a `Protocol`
   and a documentation gate exist; one could be added if a model with published validation
   evidence is found. `classifier_result` is always null.

## Consequences / residual risks
- Text embedded in a photo could try to steer the model. Mitigations: the prompt tells it to ignore
  such text, the output schema is strict, verdict language is withheld, and the label and advice
  never depend on model prose. A manipulated model could still under-report observations; the
  guidance and "cannot show safety" notes are shown regardless.
- Not tested against a real vision model in this phase.
- Rate limiting is in-process and shared with scan; cancelling in the browser does not stop
  server-side processing.
