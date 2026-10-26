import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { calculateMeal, createMeal, updateMeal } from "../../api/endpoints";
import type { Calculation, MealCategory, MealDetail } from "../../api/types";
import { CATEGORIES, toLocalInput } from "../../lib/food";
import { FormError, errorMessage } from "../FormError";
import { useToast } from "../Toast";
import { Card } from "../ui";
import { blankItem, toPayload } from "./drafts";
import type { ItemDraft } from "./drafts";
import { ItemRow } from "./ItemRow";
import { NutritionResults } from "./NutritionResults";

export interface ScanContext {
  scanRef: string;
  mediaId: string;
  notes: string | null;
  uncertaintyNote: string;
  model: string;
}

interface Props {
  initialItems: ItemDraft[];
  scan?: ScanContext | null;
  /** Present when editing a saved meal. */
  meal?: MealDetail;
}

/** Confirm/correct foods, enter portions, preview the deterministic result, then save. */
export function MealBuilder({ initialItems, scan = null, meal }: Props) {
  const navigate = useNavigate();
  const toast = useToast();
  const [items, setItems] = useState<ItemDraft[]>(initialItems);
  const [calc, setCalc] = useState<Calculation | null>(null);
  const [calcError, setCalcError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [calculating, setCalculating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [category, setCategory] = useState<MealCategory>(meal?.category ?? "lunch");
  const [eatenAt, setEatenAt] = useState(toLocalInput(meal ? new Date(meal.eaten_at) : new Date()));
  const [notes, setNotes] = useState(meal?.notes ?? "");
  const resultRef = useRef<HTMLDivElement>(null);

  // Any edit makes the previewed numbers stale, so they are hidden rather than left misleading.
  function edit(next: ItemDraft[]) {
    setItems(next);
    setCalc(null);
    setCalcError(null);
  }

  useEffect(() => {
    if (calc) resultRef.current?.focus();
  }, [calc]);

  async function onCalculate() {
    const { payload, error } = toPayload(items);
    if (items.length === 0) return setCalcError("Add at least one food first.");
    if (error) return setCalcError(error);
    setCalculating(true);
    setCalcError(null);
    try {
      setCalc(await calculateMeal(payload, scan?.scanRef ?? null, meal?.id));
    } catch (err) {
      setCalc(null);
      setCalcError(errorMessage(err));
    } finally {
      setCalculating(false);
    }
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    const { payload, error } = toPayload(items);
    if (error) return setSaveError(error);
    const when = new Date(eatenAt);
    if (Number.isNaN(when.getTime())) return setSaveError("Enter when you ate this.");
    setSaving(true);
    setSaveError(null);
    try {
      const body = {
        items: payload,
        eaten_at: when.toISOString(),
        category,
        notes: notes.trim() || null,
        scan_ref: scan?.scanRef ?? null,
        media_id: scan?.mediaId ?? meal?.media_id ?? null,
        ...(meal ? { expected_revision: meal.revision } : {}),
      };
      const saved = meal ? await updateMeal(meal.id, body) : await createMeal(body);
      toast.success(meal ? "Meal updated." : "Meal saved.");
      navigate(`/meals/${saved.id}`);
    } catch (err) {
      setSaveError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {scan && (
        <div className="alert info" role="note">
          <p>
            <strong>Check every item.</strong> {scan.uncertaintyNote}
          </p>
          {scan.notes && <p className="small-text">Model note: {scan.notes}</p>}
          <p className="small-text muted">Model-generated suggestions from “{scan.model}”. Not nutrition data.</p>
        </div>
      )}

      <Card title="1. Confirm your foods and portions" headingId="items-heading">
        <p className="hint">
          Rename, add or remove foods. A photo cannot reveal weight, so enter what you ate, or give a range
          if you are unsure.
        </p>
        {items.length === 0 ? (
          <p className="muted" role="status">
            {scan ? "The model did not find any food in this photo. " : ""}Add a food to begin.
          </p>
        ) : (
          <ul className="item-list">
            {items.map((item, i) => (
              <ItemRow key={item.key} item={item} index={i}
                onChange={(next) => edit(items.map((x) => (x.key === item.key ? next : x)))}
                onRemove={() => edit(items.filter((x) => x.key !== item.key))} />
            ))}
          </ul>
        )}
        <div className="row">
          <button type="button" className="secondary" onClick={() => edit([...items, blankItem()])}>
            Add a food
          </button>
        </div>
      </Card>

      <Card title="2. Calculate" headingId="calc-heading">
        <p className="hint">
          Values come from the food-composition sources you selected and are calculated by fixed arithmetic.
          No AI model produces or estimates nutrition numbers.
        </p>
        <FormError message={calcError} />
        <button type="button" onClick={onCalculate} disabled={calculating || items.length === 0}>
          {calculating ? "Calculating…" : "Calculate nutrition"}
        </button>
        {calc && (
          <div ref={resultRef} tabIndex={-1} className="result-focus" aria-label="Nutrition results">
            <NutritionResults calc={calc} />
          </div>
        )}
      </Card>

      {calc && (
        <Card title={meal ? "3. Save changes" : "3. Save to your meal log"} headingId="save-heading">
          <form onSubmit={onSave} noValidate>
            <div className="grid-2">
              <div>
                <label htmlFor="meal-category">Meal</label>
                <select id="meal-category" value={category} onChange={(e) => setCategory(e.target.value as MealCategory)}>
                  {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="meal-time">When did you eat?</label>
                <input id="meal-time" type="datetime-local" value={eatenAt} onChange={(e) => setEatenAt(e.target.value)} />
              </div>
            </div>
            <label htmlFor="meal-notes">Notes (optional)</label>
            <textarea id="meal-notes" rows={2} maxLength={1000} value={notes} onChange={(e) => setNotes(e.target.value)} />
            <FormError message={saveError} />
            <button type="submit" disabled={saving}>{saving ? "Saving…" : meal ? "Save changes" : "Save meal"}</button>
          </form>
        </Card>
      )}
    </>
  );
}
