import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { searchFoods } from "../../api/endpoints";
import type { FoodCandidate, NutritionSearchResponse } from "../../api/types";
import { FormError, errorMessage } from "../FormError";

const STATE_TEXT: Record<string, string> = {
  not_configured: "not set up on this server",
  unavailable: "unavailable right now",
  rate_limited: "rate limited, try again shortly",
  timeout: "timed out",
};

function summary(c: FoodCandidate): string {
  const bits: string[] = [];
  const v = c.per_100g;
  if (v.energy_kcal !== undefined) bits.push(`${v.energy_kcal} kcal`);
  if (v.protein_g !== undefined) bits.push(`${v.protein_g} g protein`);
  if (v.carbs_g !== undefined) bits.push(`${v.carbs_g} g carbs`);
  if (v.fat_g !== undefined) bits.push(`${v.fat_g} g fat`);
  return bits.length ? `Per 100 g: ${bits.join(", ")}` : "No core nutrients reported";
}

export function FoodSearch({
  initialQuery,
  onPick,
  onClose,
}: {
  initialQuery: string;
  onPick: (candidate: FoodCandidate) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<NutritionSearchResponse | null>(null);
  const latest = useRef(0);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (q.length < 2) {
      setError("Enter at least two letters.");
      return;
    }
    const mine = ++latest.current;
    setBusy(true);
    setError(null);
    try {
      const data = await searchFoods(q);
      if (mine === latest.current) setResult(data);
    } catch (err) {
      if (mine === latest.current) {
        setResult(null);
        setError(errorMessage(err));
      }
    } finally {
      if (mine === latest.current) setBusy(false);
    }
  }

  const problems = result?.sources.filter((s) => s.status !== "ok") ?? [];
  return (
    <div className="food-search" role="group" aria-label="Find nutrition data">
      <form onSubmit={submit} className="row" noValidate>
        <label className="visually-hidden" htmlFor="food-q">Search food composition data</label>
        <input id="food-q" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. cooked white rice" />
        <button type="submit" disabled={busy}>{busy ? "Searching…" : "Search"}</button>
        <button type="button" className="secondary" onClick={onClose}>Close</button>
      </form>
      <FormError message={error} />
      {problems.map((s) => (
        <p key={s.source} className="hint">
          {s.label}: {s.message ?? STATE_TEXT[s.status] ?? s.status}
        </p>
      ))}
      {result && result.results.length === 0 && (
        <p className="alert info" role="status">
          No matching foods in the sources that responded. Try a simpler name, or keep this food without
          nutrition data. Nothing is guessed.
        </p>
      )}
      {result && result.results.length > 0 && (
        <ul className="candidates">
          {result.results.map((c) => (
            <li key={c.food_ref}>
              <div>
                <p className="candidate-name">
                  {c.name}
                  {c.brand ? <span className="muted"> · {c.brand}</span> : null}
                </p>
                <p className="small-text muted">
                  {c.source_label}
                  {c.data_type ? ` · ${c.data_type}` : ""}
                  {c.serving_label ? ` · serving: ${c.serving_label}` : ""}
                </p>
                <p className="small-text">{summary(c)}</p>
                {c.notes.map((n) => (
                  <p key={n} className="small-text muted">{n}</p>
                ))}
              </div>
              <button type="button" className="secondary small" onClick={() => onPick(c)} aria-label={`Use ${c.name}`}>
                Use this
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
