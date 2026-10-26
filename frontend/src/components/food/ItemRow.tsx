import { useId, useState } from "react";
import type { FoodCandidate } from "../../api/types";
import { UNITS } from "../../lib/food";
import type { PortionDraft, PortionMode } from "../../lib/food";
import type { ItemDraft } from "./drafts";
import { FoodSearch } from "./FoodSearch";
import type { WeightUnit } from "../../api/types";

interface Props {
  item: ItemDraft;
  index: number;
  onChange: (next: ItemDraft) => void;
  onRemove: () => void;
}

function PortionFields({
  value,
  servingGrams,
  servingLabel,
  onChange,
  name,
}: {
  value: PortionDraft;
  servingGrams: number | null;
  servingLabel: string | null;
  onChange: (p: PortionDraft) => void;
  name: string;
}) {
  const id = useId();
  const set = (patch: Partial<PortionDraft>) => onChange({ ...value, ...patch });
  const unit = (
    <select aria-label={`Unit for ${name}`} value={value.unit} onChange={(e) => set({ unit: e.target.value as WeightUnit })}>
      {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
    </select>
  );
  return (
    <fieldset className="portion">
      <legend>How much did you eat?</legend>
      <label htmlFor={`${id}-mode`}>Portion type</label>
      <select id={`${id}-mode`} value={value.mode} onChange={(e) => set({ mode: e.target.value as PortionMode })}>
        <option value="weight">I know the weight</option>
        <option value="range">I can only estimate a range</option>
        <option value="servings" disabled={!servingGrams}>
          Servings{servingGrams ? ` (1 serving = ${servingGrams} g)` : " (needs a serving size from the data source)"}
        </option>
      </select>
      {value.mode === "weight" && (
        <div className="row">
          <label className="visually-hidden" htmlFor={`${id}-amount`}>Weight of {name}</label>
          <input id={`${id}-amount`} inputMode="decimal" placeholder="Weight" value={value.amount}
            onChange={(e) => set({ amount: e.target.value })} />
          {unit}
        </div>
      )}
      {value.mode === "range" && (
        <>
          <div className="row">
            <label className="visually-hidden" htmlFor={`${id}-min`}>Smallest likely weight of {name}</label>
            <input id={`${id}-min`} inputMode="decimal" placeholder="Min" value={value.min}
              onChange={(e) => set({ min: e.target.value })} />
            <span aria-hidden="true">to</span>
            <label className="visually-hidden" htmlFor={`${id}-max`}>Largest likely weight of {name}</label>
            <input id={`${id}-max`} inputMode="decimal" placeholder="Max" value={value.max}
              onChange={(e) => set({ max: e.target.value })} />
            {unit}
          </div>
          <p className="hint">Totals will be shown as a range and marked as an estimate.</p>
        </>
      )}
      {value.mode === "servings" && (
        <div className="row">
          <label className="visually-hidden" htmlFor={`${id}-count`}>Servings of {name}</label>
          <input id={`${id}-count`} inputMode="decimal" value={value.count} onChange={(e) => set({ count: e.target.value })} />
          <span className="small-text muted">× {servingLabel ?? `${servingGrams} g`}</span>
        </div>
      )}
    </fieldset>
  );
}

export function ItemRow({ item, index, onChange, onRemove }: Props) {
  const [searching, setSearching] = useState(false);
  const nameId = useId();
  const label = item.name.trim() || `food ${index + 1}`;

  function pick(c: FoodCandidate) {
    const portion =
      item.portion.mode === "servings" && !c.serving_grams ? { ...item.portion, mode: "weight" as const } : item.portion;
    onChange({ ...item, food: c, foodRef: c.food_ref, clearFood: false, portion });
    setSearching(false);
  }

  return (
    <li className="item-row">
      <div className="item-head">
        <div className="grow">
          <label htmlFor={nameId}>Food {index + 1}</label>
          <input id={nameId} value={item.name} maxLength={80} onChange={(e) => onChange({ ...item, name: e.target.value })} />
        </div>
        <button type="button" className="secondary small" onClick={onRemove} aria-label={`Remove ${label}`}>
          Remove
        </button>
      </div>

      {item.hint && (
        <div className="hint-box">
          <p className="small-text">
            <strong>Model said:</strong> {item.hint.name}
            {item.hint.ambiguous && <> · <em>the model was unsure</em></>}
            {item.hint.description && <> — {item.hint.description}</>}
          </p>
          {item.hint.alternatives.length > 0 && (
            <p className="small-text">
              Other possibilities:{" "}
              {item.hint.alternatives.map((alt) => (
                <button key={alt} type="button" className="link" onClick={() => onChange({ ...item, name: alt })}>
                  {alt}
                </button>
              ))}
            </p>
          )}
        </div>
      )}

      <div className="match">
        {item.food ? (
          <p className="small-text">
            <strong>Data:</strong> {item.food.name}
            {item.food.brand ? ` (${item.food.brand})` : ""} · {item.food.source_label}{" "}
            <button type="button" className="link" onClick={() => setSearching(true)}>Change</button>{" "}
            <button type="button" className="link"
              onClick={() => onChange({ ...item, food: null, foodRef: undefined, clearFood: true })}>
              Clear
            </button>
          </p>
        ) : (
          <p className="small-text">
            <span className="muted">No nutrition data chosen yet.</span>{" "}
            <button type="button" className="secondary small" onClick={() => setSearching(true)}
              disabled={item.name.trim().length < 2} aria-label={`Find nutrition data for ${label}`}>
              Find nutrition data
            </button>
          </p>
        )}
        {searching && <FoodSearch initialQuery={item.name} onPick={pick} onClose={() => setSearching(false)} />}
      </div>

      <PortionFields value={item.portion} name={label} servingGrams={item.food?.serving_grams ?? null}
        servingLabel={item.food?.serving_label ?? null} onChange={(portion) => onChange({ ...item, portion })} />
    </li>
  );
}
