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

export function PreferencesForm() {
  const [options, setOptions] = useState<PreferenceOptions | null>(null);
  const [unit, setUnit] = useState<UnitSystem>("metric");
  const [diet, setDiet] = useState<string[]>([]);
  const [allergies, setAllergies] = useState<string[]>([]);
  const [newAllergy, setNewAllergy] = useState("");
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
      });
      setUnit(result.unit_system);
      setDiet(result.dietary_preferences);
      setAllergies(result.allergies);
      setSaved(true);
    } catch (err) {
      setSaveError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (loadError) return <p className="alert error" role="alert">{loadError}</p>;
  if (!options) return <Loading label="Loading preferences…" />;

  const suggestions = options.common_allergens.filter((a) => !allergies.includes(a));

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
          {suggestions.length > 0 && (
            <p className="hint">
              Common:{" "}
              {suggestions.map((s) => (
                <button key={s} type="button" className="link"
                  onClick={() => { setAllergies([...allergies, s]); setSaved(false); }}>
                  {s}
                </button>
              ))}
            </p>
          )}
        </fieldset>

        <FormError message={saveError} />
        {saved && <p className="alert ok" role="status">Preferences saved.</p>}
        <button type="submit" disabled={busy}>{busy ? "Saving…" : "Save preferences"}</button>
      </form>
    </Card>
  );
}
