import type {
  HygieneCategory, HygieneCertainty, HygieneSeverity, HygieneStatus,
} from "../api/types";

export const SEVERITY_LABELS: Record<HygieneSeverity, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
};

export const SEVERITY_TONE: Record<HygieneSeverity, "neutral" | "ok" | "warn"> = {
  low: "neutral",
  medium: "warn",
  high: "warn",
};

export const STATUS_TONE: Record<HygieneStatus, "neutral" | "ok" | "warn"> = {
  draft: "neutral",
  in_review: "neutral",
  approved: "ok",
  rejected: "warn",
};

export const CERTAINTY_LABELS: Record<HygieneCertainty, string> = {
  clearly_visible: "Clearly visible",
  possibly_visible: "Possibly visible",
};

export const CATEGORY_LABELS: Record<HygieneCategory, string> = {
  surface_cleanliness: "Surface cleanliness",
  uncovered_food: "Uncovered food",
  raw_ready_to_eat_separation: "Raw / ready-to-eat separation",
  waste_management: "Waste management",
  tool_cleanliness: "Tool cleanliness",
  other_visible_concern: "Other visible concern",
};

export const CATEGORY_OPTIONS: { value: HygieneCategory; label: string }[] =
  (Object.keys(CATEGORY_LABELS) as HygieneCategory[]).map((v) => ({ value: v, label: CATEGORY_LABELS[v] }));

export const SOURCE_LABEL: Record<string, string> = {
  model: "Model observation",
  user: "User-added observation",
  user_edited: "Model observation (edited by you)",
};