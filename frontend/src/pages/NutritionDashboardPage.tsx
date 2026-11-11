import { useCallback, useState } from "react";
import type { FormEvent } from "react";
import {
  clearNutritionTarget, getNutritionTarget, getTracking, setNutritionTarget,
} from "../api/endpoints";
import type { NutritionTarget, Tracking } from "../api/types";
import { FormError, errorMessage } from "../components/FormError";
import { useToast } from "../components/Toast";
import { Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { toISODate, shiftDays } from "../lib/week";

/** Simple SVG bar chart. Only rendered when `tracking.chart_available` is true. */
function BarChart({ tracking }: { tracking: Tracking }) {
  const width = 640;
  const height = 220;
  const padding = { top: 24, right: 16, bottom: 28, left: 48 };
  const max = Math.max(
    tracking.target_kcal ?? 0,
    ...tracking.days.map((d) => d.kcal_high || 0),
    1,
  );
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const bw = plotW / tracking.days.length - 6;
  const targetY = tracking.target_kcal
    ? padding.top + plotH - (tracking.target_kcal / max) * plotH
    : null;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img"
      aria-label="Calories consumed per day, drawn only from logged meals">
      <line x1={padding.left} y1={padding.top + plotH} x2={width - padding.right}
        y2={padding.top + plotH} stroke="var(--line)" />
      {targetY !== null && (
        <line x1={padding.left} y1={targetY} x2={width - padding.right} y2={targetY}
          stroke="var(--citrus)" strokeDasharray="4 3" />
      )}
      {tracking.days.map((d, i) => {
        const x = padding.left + i * (plotW / tracking.days.length) + 3;
        const h = d.kcal_high ? (d.kcal_high / max) * plotH : 0;
        const y = padding.top + plotH - h;
        return (
          <g key={d.date}>
            <rect x={x} y={y} width={bw} height={h}
              fill={d.complete ? "var(--brand)" : "var(--citrus)"} rx={3} />
            <text x={x + bw / 2} y={height - 8} fontSize={10} textAnchor="middle"
              fill="var(--muted)">{d.date.slice(5)}</text>
          </g>
        );
      })}
      <text x={padding.left - 8} y={padding.top + 4} fontSize={10} textAnchor="end"
        fill="var(--muted)">{Math.round(max)}</text>
      <text x={padding.left - 8} y={padding.top + plotH} fontSize={10} textAnchor="end"
        fill="var(--muted)">0</text>
    </svg>
  );
}

export function NutritionDashboardPage() {
  const toast = useToast();
  const [daysBack, setDaysBack] = useState(14);
  const [targetDraft, setTargetDraft] = useState<NutritionTarget | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const target = useResource(useCallback(() => getNutritionTarget(), []));
  const from = toISODate(shiftDays(new Date(), -daysBack + 1));
  const to = toISODate(new Date());
  const tracking = useResource(useCallback(() => getTracking(from, to), [from, to]));

  function startEdit() {
    setTargetDraft(target.data ?? {
      calories_min: null, calories_max: null, protein_g_min: null,
      carbs_g_min: null, fat_g_min: null, fiber_g_min: null, notes: null,
    });
  }

  async function saveTarget(e: FormEvent) {
    e.preventDefault();
    if (!targetDraft) return;
    setBusy(true);
    setError(null);
    try {
      await setNutritionTarget(targetDraft);
      toast.success("Target saved.");
      target.reload();
      tracking.reload();
      setTargetDraft(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function clearTarget() {
    setBusy(true);
    try {
      await clearNutritionTarget();
      toast.success("Target cleared.");
      target.reload();
      tracking.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Nutrition tracking"
        description="Compare calories from your logged meals against a target you set yourself. Nothing here is inferred from your data." />

      <Card title="Your target" headingId="target-h">
        {target.error ? (
          <ErrorState error={target.error} onRetry={target.reload} />
        ) : !target.data ? (
          <Loading />
        ) : targetDraft ? (
          <form onSubmit={saveTarget} noValidate>
            <div className="grid-2">
              {(["calories_min", "calories_max"] as const).map((k) => (
                <div key={k}>
                  <label htmlFor={k}>{k === "calories_min" ? "Calories (min)" : "Calories (max)"}</label>
                  <input id={k} type="number" min={0} max={20000}
                    value={targetDraft[k] ?? ""}
                    onChange={(e) => setTargetDraft({
                      ...targetDraft, [k]: e.target.value === "" ? null : Number(e.target.value),
                    })} />
                </div>
              ))}
              {(["protein_g_min", "carbs_g_min", "fat_g_min", "fiber_g_min"] as const).map((k) => (
                <div key={k}>
                  <label htmlFor={k}>{k.replace("_g_min", "")} (g, min)</label>
                  <input id={k} type="number" min={0} max={2000}
                    value={targetDraft[k] ?? ""}
                    onChange={(e) => setTargetDraft({
                      ...targetDraft, [k]: e.target.value === "" ? null : Number(e.target.value),
                    })} />
                </div>
              ))}
            </div>
            <label htmlFor="target-notes">Notes</label>
            <input id="target-notes" maxLength={500} value={targetDraft.notes ?? ""}
              onChange={(e) => setTargetDraft({ ...targetDraft, notes: e.target.value || null })} />
            <FormError message={error} />
            <div className="row wrap">
              <button type="submit" disabled={busy}>{busy ? "Saving…" : "Save target"}</button>
              <button type="button" className="secondary" onClick={() => setTargetDraft(null)}>Cancel</button>
              <button type="button" className="secondary" onClick={clearTarget} disabled={busy}>Clear</button>
            </div>
          </form>
        ) : target.data.calories_min === null && target.data.calories_max === null ? (
          <>
            <p className="muted">No target set. You decide what (if anything) to track.</p>
            <button type="button" onClick={startEdit}>Set a target</button>
          </>
        ) : (
          <>
            <p>
              {target.data.calories_min !== null && <>min {target.data.calories_min} kcal </>}
              {target.data.calories_max !== null && <>max {target.data.calories_max} kcal </>}
              {target.data.protein_g_min !== null && <>· protein ≥ {target.data.protein_g_min} g </>}
              {target.data.carbs_g_min !== null && <>· carbs ≥ {target.data.carbs_g_min} g </>}
              {target.data.fat_g_min !== null && <>· fat ≥ {target.data.fat_g_min} g </>}
              {target.data.fiber_g_min !== null && <>· fibre ≥ {target.data.fiber_g_min} g</>}
            </p>
            {target.data.notes && <p className="small-text muted">{target.data.notes}</p>}
            <div className="row wrap">
              <button type="button" className="secondary" onClick={startEdit}>Edit target</button>
              <button type="button" className="secondary" onClick={clearTarget} disabled={busy}>
                Clear target
              </button>
            </div>
          </>
        )}
      </Card>

      <Card title="Last days" headingId="chart-h">
        <div className="toolbar">
          <label htmlFor="days-back">Range</label>
          <select id="days-back" value={daysBack} onChange={(e) => setDaysBack(Number(e.target.value))}>
            <option value={7}>Last 7 days</option>
            <option value={14}>Last 14 days</option>
            <option value={30}>Last 30 days</option>
          </select>
        </div>
        {tracking.error ? (
          <ErrorState error={tracking.error} onRetry={tracking.reload} />
        ) : !tracking.data ? (
          <Loading />
        ) : !Array.isArray(tracking.data.days) ? (
          <p className="alert error" role="alert">
            The tracking data was malformed. Try again.
          </p>
        ) : tracking.data.days_with_data === 0 ? (
          <EmptyState title="No consumed meals in this range"
            description="Log meals in the meal log and they will appear here." />
        ) : (
          <>
            {tracking.data.chart_available ? (
              <BarChart tracking={tracking.data} />
            ) : (
              <p className="alert info" role="note">
                Charts appear once at least 3 days in the range have logged meals. You have{" "}
                {tracking.data.days_with_data} so far.
              </p>
            )}
            <table className="nutrient-table">
              <caption>Logged calories per day</caption>
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">Meals</th>
                  <th scope="col">Calories (kcal)</th>
                  <th scope="col">Coverage</th>
                </tr>
              </thead>
              <tbody>
                {tracking.data.days.map((d) => (
                  <tr key={d.date}>
                    <th scope="row">{d.date}</th>
                    <td>{d.meals_logged}</td>
                    <td>{d.meals_logged === 0 ? "—" : Math.round(d.kcal_low)}</td>
                    <td className="small-text">
                      {d.meals_logged === 0 ? "No meals" :
                        d.complete ? "All logged meals included" :
                        <span className="partial">Partial (some meals missing data)</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="small-text muted">{tracking.data.note}</p>
          </>
        )}
      </Card>
    </>
  );
}