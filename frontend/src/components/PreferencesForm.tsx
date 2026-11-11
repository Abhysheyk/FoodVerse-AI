import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { getPreferenceOptions, getPreferences, updatePreferences } from "../api/endpoints";
import type { PreferenceOptions, UnitSystem } from "../api/types";
import { FormError, errorMessage } from "../components/FormError";
import { Card, Loading } from "../components/ui";

const LABELS: Record<string, string> = {
  gluten_free: "Gluten-free",
  lactose_free: "Lactose-free",
};
const label = (v: string) => LABELS[v] ?? v.charAt(0).toUpperCase() + v.slice(1);

/**
 * Small reusable chip-list editor: add via Enter or the Add button, remove via ×.
 * Values are stored lower-cased and de-duplicated by the caller (backend re-validates).
 */
function ChipList({
  id,
  legend,
  hint,
  values,
  onAdd,
  onRemove,
  placeholder,
  maxLength = 50,
}: {
  id: string;
  legend: string;
  hint?: string;
  values: string[];
  onAdd: (value: string) => void;
  onRemove: (value: string) => void;
  placeholder: string;
  maxLength?: number;
}) {
  const [draft, setDraft] = useState("");
  const commit = () => {
    const value = draft.trim().toLowerCase();
    if (value) onAdd(value);
    setDraft("");
  };
  return (
    <fieldset>
      <legend>{legend}</legend>
      {hint && <p className="hint">{hint}</p>}
      <ul className="chips" aria-label={legend}>
        {values.length === 0 && <li className="hint">None added</li>}
        {values.map((value) => (
          <li key={value}>
            {value}
            <button type="button" className="chip-remove"
              aria-label={`Remove ${value}`} onClick={() => onRemove(value)}>
              ×
            </button>
          </li>
        ))}
      </ul>
      <div className="row">
        <label htmlFor={`add-${id}`} className="visually-hidden">{legend}</label>
        <input id={`add-${id}`} value={draft} maxLength={maxLength} placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commit();
            }
          }} />
        <button type="button" className="secondary" onClick={commit} aria-label={`Add ${legend}`}>
          Add
        </button>
      </div>
    </fieldset>
  );
}

export function PreferencesForm() {
  const [options, setOptions] = useState<PreferenceOptions | null>(null);

  // Phase 1–2 fields
  const [unit, setUnit] = useState<UnitSystem>("metric");
  const [diet, setDiet] = useState<string[]>([]);
  const [allergies, setAllergies] = useState<string[]>([]);
  const [newAllergy, setNewAllergy] = useState("");

  // Phase 7 fields
  const [pattern, setPattern] = useState<string>("omnivore");
  const [excluded, setExcluded] = useState<string[]>([]);
  const [cuisines, setCuisines] = useState<string[]>([]);
  const [budget, setBudget] = useState<string>("any");
  const [maxMinutes, setMaxMinutes] = useState<number | null>(null);
  const [servings, setServings] = useState<number>(1);
  const [pantry, setPantry] = useState<string[]>([]);

  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getPreferenceOptions(), getPreferences()])
      .then(([opts, prefs]) => {
        if (cancelled) return;
        setOptions(opts);
        setUnit(prefs.unit_system);
        setDiet(prefs.dietary_preferences);
        setAllergies(prefs.allergies);
        setPattern(prefs.dietary_pattern ?? "omnivore");
        setExcluded(prefs.excluded_ingredients ?? []);
        setCuisines(prefs.preferred_cuisines ?? []);
        setBudget(prefs.budget ?? "any");
        setMaxMinutes(prefs.max_cooking_minutes ?? null);
        setServings(prefs.default_servings ?? 1);
        setPantry(prefs.pantry_ingredients ?? []);
      })
      .catch((e) => !cancelled && setLoadError(errorMessage(e)));
    return () => {
      cancelled = true;
    };
  }, []);

  const toggle = (list: string[], value: string) =>
    list.includes(value) ? list.filter((x) => x !== value) : [...list, value];

  function addAllergy() {
    const value = newAllergy.trim().replace(/\s+/g, " ").toLowerCase();
    if (value && !allergies.includes(value)) setAllergies([...allergies, value]);
    setNewAllergy("");
    setSaved(false);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaveError(null);
    setSaved(false);
    setBusy(true);
    try {
      const result = await updatePreferences({
        unit_system: unit,
        dietary_preferences: diet,
        allergies,
        dietary_pattern: pattern,
        excluded_ingredients: excluded,
        preferred_cuisines: cuisines,
        budget,
        max_cooking_minutes: maxMinutes,
        default_servings: servings,
        pantry_ingredients: pantry,
      });
      setUnit(result.unit_system);
      setDiet(result.dietary_preferences);
      setAllergies(result.allergies);
      setPattern(result.dietary_pattern ?? "omnivore");
      setExcluded(result.excluded_ingredients ?? []);
      setCuisines(result.preferred_cuisines ?? []);
      setBudget(result.budget ?? "any");
      setMaxMinutes(result.max_cooking_minutes ?? null);
      setServings(result.default_servings ?? 1);
      setPantry(result.pantry_ingredients ?? []);
      setSaved(true);
    } catch (err) {
      setSaveError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (loadError) return <p className="alert error" role="alert">{loadError}</p>;
  if (!options) return <Loading label="Loading preferences…" />;

  const allergySuggestions = options.common_allergens.filter((a) => !allergies.includes(a));

  return (
    <Card title="Food preferences" headingId="prefs-heading">
      <form onSubmit={handleSubmit} onChange={() => setSaved(false)}>
        <fieldset>
          <legend>Units</legend>
          {options.unit_systems.map((u) => (
            <label key={u} className="inline">
              <input type="radio" name="unit" value={u} checked={unit === u}
                onChange={() => setUnit(u)} />
              {label(u)}
            </label>
          ))}
        </fieldset>

        <fieldset>
          <legend>Dietary preferences</legend>
          {options.dietary_preferences.map((d) => (
            <label key={d} className="inline">
              <input type="checkbox" checked={diet.includes(d)}
                onChange={() => setDiet(toggle(diet, d))} />
              {label(d)}
            </label>
          ))}
        </fieldset>

        <fieldset>
          <legend>Allergies</legend>
          <p className="hint">
            Declared by you and used only to flag foods. Always check packaging and ask when eating
            out; this app cannot guarantee a food is allergen-free.
          </p>
          <ul className="chips" aria-label="Your allergies">
            {allergies.length === 0 && <li className="hint">None added</li>}
            {allergies.map((a) => (
              <li key={a}>
                {a}
                <button type="button" className="chip-remove" aria-label={`Remove ${a}`}
                  onClick={() => { setAllergies(allergies.filter((x) => x !== a)); setSaved(false); }}>
                  ×
                </button>
              </li>
            ))}
          </ul>
          <div className="row">
            <label htmlFor="new-allergy" className="visually-hidden">Add an allergy</label>
            <input id="new-allergy" value={newAllergy} maxLength={50} placeholder="e.g. peanut"
              onChange={(e) => setNewAllergy(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addAllergy(); } }} />
            <button type="button" className="secondary" onClick={addAllergy}>Add</button>
          </div>
          {allergySuggestions.length > 0 && (
            <p className="hint">
              Common:{" "}
              {allergySuggestions.map((s) => (
                <button key={s} type="button" className="link"
                  onClick={() => { setAllergies([...allergies, s]); setSaved(false); }}>
                  {s}
                </button>
              ))}
            </p>
          )}
        </fieldset>

        {/* ---------- Phase 7 additions ---------- */}

        <fieldset>
          <legend>Dietary pattern</legend>
          <p className="hint">
            Used to filter meal-plan suggestions. Patterns marked “(advisory)” cannot be enforced by
            keyword matching — use excluded ingredients for stricter control.
          </p>
          <label htmlFor="diet-pattern" className="visually-hidden">Dietary pattern</label>
          <select id="diet-pattern" value={pattern} onChange={(e) => setPattern(e.target.value)}>
            {(options.dietary_patterns ?? ["omnivore"]).map((p) => (
              <option key={p} value={p}>
                {p}
                {p === "halal" || p === "kosher" ? " (advisory)" : ""}
              </option>
            ))}
          </select>
        </fieldset>

        <fieldset>
          <legend>Budget</legend>
          <label htmlFor="budget" className="visually-hidden">Budget level</label>
          <select id="budget" value={budget} onChange={(e) => setBudget(e.target.value)}>
            {(options.budget_levels ?? ["any"]).map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
        </fieldset>

        <fieldset>
          <legend>Cooking time and servings</legend>
          <label htmlFor="max-minutes">Maximum cooking time per meal (minutes)</label>
          <input id="max-minutes" type="number" min={5} max={720}
            value={maxMinutes ?? ""} placeholder="No limit"
            onChange={(e) =>
              setMaxMinutes(e.target.value === "" ? null : Number(e.target.value))
            } />
          <label htmlFor="default-servings">Default servings per meal</label>
          <input id="default-servings" type="number" min={1} max={20} value={servings}
            onChange={(e) => setServings(Number(e.target.value) || 1)} />
        </fieldset>

        <ChipList
          id="excluded"
          legend="Excluded ingredients"
          hint="Never used in AI meal-plan suggestions, and enforced in code."
          values={excluded}
          onAdd={(v) => setExcluded([...excluded, v])}
          onRemove={(v) => setExcluded(excluded.filter((x) => x !== v))}
          placeholder="e.g. onion"
          maxLength={50}
        />

        <ChipList
          id="cuisine"
          legend="Preferred cuisines"
          values={cuisines}
          onAdd={(v) => setCuisines([...cuisines, v])}
          onRemove={(v) => setCuisines(cuisines.filter((x) => x !== v))}
          placeholder="e.g. south indian"
          maxLength={32}
        />

        <ChipList
          id="pantry"
          legend="Ingredients you already have"
          hint="Suggested to the plan generator so it can favour what is already in your pantry."
          values={pantry}
          onAdd={(v) => setPantry([...pantry, v])}
          onRemove={(v) => setPantry(pantry.filter((x) => x !== v))}
          placeholder="e.g. rice"
          maxLength={80}
        />

        <FormError message={saveError} />
        {saved && <p className="alert ok" role="status">Preferences saved.</p>}
        <button type="submit" disabled={busy}>{busy ? "Saving…" : "Save preferences"}</button>
      </form>
    </Card>
  );
}