import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { PlanDay, PlanIngredient, PlanMeal } from "../../api/types";
import { FormError } from "../FormError";

const UNITS = ["g", "kg", "oz", "lb", "ml", "l", "tsp", "tbsp", "cup", "piece", "slice", "clove", "pinch"];
const CATEGORIES: PlanMeal["meal"][] = ["breakfast", "lunch", "dinner", "snack"];

interface Props {
  open: boolean;
  day: PlanDay;
  meal: PlanMeal | null; // null = new
  onSave: (meal: PlanMeal) => Promise<void> | void;
  onDelete?: () => Promise<void> | void;
  onCancel: () => void;
}

function blank(): PlanMeal {
  return {
    meal: "lunch",
    title: "",
    servings: 1,
    cooking_minutes: null,
    ingredients: [],
    notes: null,
  };
}

/** Full-screen editable dialog with focus trap and Escape support. */
export function MealEditorDialog({ open, day, meal, onSave, onDelete, onCancel }: Props) {
  const titleId = useId();
  const descId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const firstRef = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState<PlanMeal>(meal ?? blank());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setDraft(meal ?? blank());
    const opener = document.activeElement as HTMLElement | null;
    // Defer to allow the dialog to mount before focusing.
    window.setTimeout(() => firstRef.current?.focus(), 0);
    return () => opener?.focus?.();
  }, [open, meal]);

  if (!open) return null;

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape" && !busy) {
      e.stopPropagation();
      onCancel();
      return;
    }
    if (e.key !== "Tab") return;
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
      "input:not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled])",
    );
    if (!focusable || focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  function setIngredient(idx: number, patch: Partial<PlanIngredient>) {
    setDraft((d) => ({
      ...d,
      ingredients: d.ingredients.map((i, x) => (x === idx ? { ...i, ...patch } : i)),
    }));
  }

  function addIngredient() {
    setDraft((d) => ({ ...d, ingredients: [...d.ingredients, { name: "", quantity: 1, unit: "g" }] }));
  }

  function removeIngredient(idx: number) {
    setDraft((d) => ({ ...d, ingredients: d.ingredients.filter((_, x) => x !== idx) }));
  }

  async function save() {
    setError(null);
    if (!draft.title.trim()) return setError("Give the meal a title.");
    if (draft.ingredients.length === 0) return setError("Add at least one ingredient.");
    for (const [i, ing] of draft.ingredients.entries()) {
      if (!ing.name.trim()) return setError(`Ingredient ${i + 1} needs a name.`);
      if (!(ing.quantity > 0)) return setError(`Ingredient ${i + 1} needs a positive quantity.`);
      if (!UNITS.includes(ing.unit)) return setError(`Ingredient ${i + 1} has an unsupported unit.`);
    }
    setBusy(true);
    try {
      await onSave({
        ...draft,
        title: draft.title.trim(),
        ingredients: draft.ingredients.map((i) => ({
          name: i.name.trim(),
          quantity: i.quantity,
          unit: i.unit,
        })),
        notes: draft.notes?.trim() || null,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!onDelete) return;
    setBusy(true);
    try {
      await onDelete();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && !busy && onCancel()}>
      <div
        ref={dialogRef}
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        onKeyDown={onKeyDown}
        style={{ width: "min(640px, 100%)" }}
      >
        <h2 id={titleId}>{meal ? "Edit meal" : "Add meal"}</h2>
        <p id={descId} className="muted small-text">
          {day.day_date}. Every ingredient must include a name, a positive quantity and a supported unit.
        </p>

        <label htmlFor="meal-kind">Meal</label>
        <select id="meal-kind" value={draft.meal}
          onChange={(e) => setDraft({ ...draft, meal: e.target.value as PlanMeal["meal"] })}>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>

        <label htmlFor="meal-title">Title</label>
        <input ref={firstRef} id="meal-title" maxLength={160} value={draft.title}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })} />

        <div className="grid-2">
          <div>
            <label htmlFor="meal-servings">Servings</label>
            <input id="meal-servings" type="number" min={1} max={20} value={draft.servings}
              onChange={(e) => setDraft({ ...draft, servings: Number(e.target.value) || 1 })} />
          </div>
          <div>
            <label htmlFor="meal-minutes">Cooking time (minutes)</label>
            <input id="meal-minutes" type="number" min={1} max={1440}
              value={draft.cooking_minutes ?? ""}
              onChange={(e) =>
                setDraft({ ...draft, cooking_minutes: e.target.value === "" ? null : Number(e.target.value) })
              } />
          </div>
        </div>

        <fieldset>
          <legend>Ingredients</legend>
          <ul className="item-list" style={{ margin: 0 }}>
            {draft.ingredients.map((ing, idx) => (
              <li key={idx} className="row wrap" style={{ gap: ".5rem" }}>
                <label className="visually-hidden" htmlFor={`ing-${idx}-name`}>Ingredient name</label>
                <input id={`ing-${idx}-name`} placeholder="e.g. tomato" value={ing.name}
                  onChange={(e) => setIngredient(idx, { name: e.target.value })} />
                <label className="visually-hidden" htmlFor={`ing-${idx}-qty`}>Quantity</label>
                <input id={`ing-${idx}-qty`} type="number" min={0.01} step="0.01" style={{ maxWidth: 100 }}
                  value={ing.quantity}
                  onChange={(e) => setIngredient(idx, { quantity: Number(e.target.value) })} />
                <label className="visually-hidden" htmlFor={`ing-${idx}-unit`}>Unit</label>
                <select id={`ing-${idx}-unit`} value={ing.unit}
                  onChange={(e) => setIngredient(idx, { unit: e.target.value })}>
                  {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
                </select>
                <button type="button" className="secondary small" onClick={() => removeIngredient(idx)}>
                  Remove
                </button>
              </li>
            ))}
          </ul>
          <button type="button" className="secondary" onClick={addIngredient}>Add ingredient</button>
        </fieldset>

        <label htmlFor="meal-notes">Notes (optional)</label>
        <textarea id="meal-notes" rows={2} maxLength={400} value={draft.notes ?? ""}
          onChange={(e) => setDraft({ ...draft, notes: e.target.value || null })} />

        <FormError message={error} />

        <div className="dialog-actions">
          {onDelete && (
            <button type="button" className="danger" onClick={remove} disabled={busy}>Delete meal</button>
          )}
          <button type="button" className="secondary" onClick={onCancel} disabled={busy}>Cancel</button>
          <button type="button" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </div>
    </div>
  );
}