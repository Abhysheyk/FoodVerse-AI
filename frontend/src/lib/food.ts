import type { MealCategory, PortionInput, WeightUnit } from "../api/types";

export const CATEGORIES: { value: MealCategory; label: string }[] = [
  { value: "breakfast", label: "Breakfast" },
  { value: "lunch", label: "Lunch" },
  { value: "dinner", label: "Dinner" },
  { value: "snack", label: "Snack" },
];

export const categoryLabel = (c: MealCategory) => CATEGORIES.find((x) => x.value === c)?.label ?? c;

export const UNITS: WeightUnit[] = ["g", "kg", "oz", "lb"];

const num = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });

/** "78 kcal", or "52–104 kcal" when the value is an estimated range. */
export function formatAmount(low: number, high: number, unit: string): string {
  return low === high ? `${num.format(low)} ${unit}` : `${num.format(low)}–${num.format(high)} ${unit}`;
}

export const WARNING_TEXT: Record<string, string> = {
  no_nutrition_data: "No nutrition source was chosen for this food, so no values are shown.",
  portion_missing: "No portion was entered, so no values are shown.",
  portion_is_estimate: "The portion is your estimate, so values are shown as a range.",
  partial_nutrients: "The source does not report every core nutrient for this food.",
};

export const SUMMARY_WARNING_TEXT: Record<string, string> = {
  incomplete_totals:
    "Some totals are partial: at least one food is missing data for that nutrient, so the total is a lower bound, not the full amount.",
  estimated_portions: "At least one portion is an estimated range, so totals are ranges.",
  no_nutrition_data: "None of the foods has nutrition data, so there are no totals.",
};

/** Local "YYYY-MM-DDTHH:mm" for <input type="datetime-local">. */
export function toLocalInput(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

// ---- portion drafts (what the user is typing) ----
export type PortionMode = "none" | "weight" | "range" | "servings";

export interface PortionDraft {
  mode: PortionMode;
  amount: string;
  min: string;
  max: string;
  count: string;
  unit: WeightUnit;
}

export const emptyPortion = (): PortionDraft => ({
  mode: "weight",
  amount: "",
  min: "",
  max: "",
  count: "1",
  unit: "g",
});

export function draftFromPortion(p: PortionInput | null): PortionDraft {
  const base = emptyPortion();
  if (!p) return base;
  if (p.kind === "weight") return { ...base, mode: "weight", amount: String(p.amount), unit: p.unit };
  if (p.kind === "range") return { ...base, mode: "range", min: String(p.min_amount), max: String(p.max_amount), unit: p.unit };
  return { ...base, mode: "servings", count: String(p.count) };
}

const positive = (text: string): number | null => {
  const value = Number(text.trim());
  return text.trim() !== "" && Number.isFinite(value) && value > 0 ? value : null;
};

/** Returns the portion to send, null when none was entered, or an error message. */
export function portionFromDraft(d: PortionDraft): { portion: PortionInput | null; error: string | null } {
  if (d.mode === "none") return { portion: null, error: null };
  if (d.mode === "weight") {
    if (d.amount.trim() === "") return { portion: null, error: null };
    const amount = positive(d.amount);
    return amount === null
      ? { portion: null, error: "Enter a weight greater than zero." }
      : { portion: { kind: "weight", amount, unit: d.unit }, error: null };
  }
  if (d.mode === "range") {
    if (d.min.trim() === "" && d.max.trim() === "") return { portion: null, error: null };
    const min = positive(d.min);
    const max = positive(d.max);
    if (min === null || max === null) return { portion: null, error: "Enter both a minimum and a maximum above zero." };
    if (min >= max) return { portion: null, error: "The minimum must be smaller than the maximum." };
    return { portion: { kind: "range", min_amount: min, max_amount: max, unit: d.unit }, error: null };
  }
  const count = positive(d.count);
  return count === null
    ? { portion: null, error: "Enter a number of servings greater than zero." }
    : { portion: { kind: "servings", count }, error: null };
}
