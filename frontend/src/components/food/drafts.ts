import type { FoodItemPayload, FoodSnapshot, ItemCalculation, ObservedFood } from "../../api/types";
import { draftFromPortion, emptyPortion, portionFromDraft } from "../../lib/food";
import type { PortionDraft } from "../../lib/food";

/** One food as the user is editing it. Nutrient numbers never live here: only a signed reference. */
export interface ItemDraft {
  key: string;
  itemId?: string; // existing item of a saved meal
  observedId?: number; // index in the scan result
  name: string;
  hint?: ObservedFood; // what the model said, shown beside the editable name
  food: FoodSnapshot | null;
  foodRef?: string; // set only when the user picked a (new) match this session
  clearFood: boolean;
  portion: PortionDraft;
}

let counter = 0;
export const newKey = () => `item-${++counter}`;

export const blankItem = (): ItemDraft => ({ key: newKey(), name: "", food: null, clearFood: false, portion: emptyPortion() });

export const draftFromObserved = (o: ObservedFood): ItemDraft => ({
  key: newKey(),
  observedId: o.observed_id,
  name: o.name,
  hint: o,
  food: null,
  clearFood: false,
  portion: emptyPortion(),
});

export const draftFromSaved = (i: ItemCalculation): ItemDraft => ({
  key: newKey(),
  itemId: i.item_id,
  name: i.name,
  food: i.food,
  clearFood: false,
  portion: draftFromPortion(i.portion_input),
});

/** Convert drafts to the API payload, or return the first problem to show the user. */
export function toPayload(items: ItemDraft[]): { payload: FoodItemPayload[]; error: string | null } {
  const payload: FoodItemPayload[] = [];
  for (const d of items) {
    const name = d.name.trim();
    if (!name) return { payload: [], error: "Every food needs a name. Remove empty rows or fill them in." };
    const { portion, error } = portionFromDraft(d.portion);
    if (error) return { payload: [], error: `${name}: ${error}` };
    const p: FoodItemPayload = { name };
    if (d.itemId) p.item_id = d.itemId;
    if (d.observedId !== undefined) p.observed_id = d.observedId;
    if (d.foodRef) p.food_ref = d.foodRef;
    else if (d.clearFood) p.clear_food = true;
    if (portion) p.portion = portion;
    payload.push(p);
  }
  return { payload, error: null };
}
