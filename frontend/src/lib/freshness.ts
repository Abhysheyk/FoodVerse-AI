import type { AdviceLevel, FreshnessLabel } from "../api/types";

/**
 * Labels describe one image, never the food. Deliberately no "safe" / "fresh" / green anywhere:
 * the best outcome is neutral, a concern is a warning, and inconclusive is neutral.
 */
export const LABEL_TONE: Record<FreshnessLabel, "neutral" | "warn"> = {
  visible_concern_observed: "warn",
  no_obvious_visible_concern: "neutral",
  inconclusive: "neutral",
};

export const LABEL_FILTERS: { value: FreshnessLabel; label: string }[] = [
  { value: "visible_concern_observed", label: "Visible concern observed" },
  { value: "no_obvious_visible_concern", label: "No obvious visible concern in this image" },
  { value: "inconclusive", label: "Inconclusive" },
];

export const ADVICE_CLASS: Record<AdviceLevel, string> = {
  discard_recommended: "alert error",
  use_caution: "alert warn",
  general_caution: "alert info",
};

export const QUALITY_TEXT: Record<string, string> = {
  clear: "clear",
  limited: "limited",
  unusable: "too unclear to judge",
};

export const SEVERITY_TEXT: Record<string, string> = {
  slight: "slight",
  moderate: "moderate",
  marked: "marked",
};

export const CERTAINTY_TEXT: Record<string, string> = {
  clearly_visible: "clearly visible",
  possibly_visible: "possibly visible",
};

export const MATCH_TEXT: Record<string, string> = {
  yes: "matches the food you named",
  no: "does not match the food you named",
  unsure: "the model was unsure it matches the food you named",
};

export function localDate(date = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
