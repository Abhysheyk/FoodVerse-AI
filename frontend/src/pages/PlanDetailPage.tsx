import { useCallback, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import {
  copyMealPlan, createGroceryList, deleteMealPlan, estimateMealPlan,
  getMealPlan, updateMealPlan,
} from "../api/endpoints";
import type { PlanBody, PlanEstimateDay, PlanDetail, PlanMeal } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FormError, errorMessage } from "../components/FormError";
import { PlanDayCard } from "../components/plan/PlanDayCard";
import { MealEditorDialog } from "../components/plan/MealEditorDialog";
import { useToast } from "../components/Toast";
import { Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { dayLabel } from "../lib/week";
const CATEGORIES: PlanMeal["meal"][] = ["breakfast", "lunch", "dinner", "snack"];

export function PlanDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const plan = useResource(useCallback(() => getMealPlan(id), [id]));
  const [editSlot, setEditSlot] = useState<{ dayIdx: number; mealIdx: number | null } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [copyWeek, setCopyWeek] = useState("");
  const [copying, setCopying] = useState(false);


  async function persist(nextPlan: PlanDetail) {
    const body: PlanBody = {
      title: nextPlan.title,
      week_start_date: nextPlan.week_start_date,
      notes: nextPlan.notes,
      days: nextPlan.plan.days,
      expected_revision: nextPlan.revision,
    };
    try {
      setError(null);
      const saved = await updateMealPlan(nextPlan.id, body);
      plan.reload();
      return saved;
    } catch (err) {
      if (err instanceof ApiError && err.code === "meal_plan_constraint_violation") {
        setError("This change breaks a hard constraint. Nothing was saved.");
      } else {
        setError(errorMessage(err));
      }
      return null;
    }
  }

  async function onMealSave(dayIdx: number, mealIdx: number | null, meal: PlanMeal | null) {
    if (!plan.data) return;
    const days = [...plan.data.plan.days];
    const day = { ...days[dayIdx], meals: [...days[dayIdx].meals] };
    if (meal === null) {
      if (mealIdx !== null) day.meals.splice(mealIdx, 1);
    } else if (mealIdx === null) {
      day.meals.push(meal);
    } else {
      day.meals[mealIdx] = meal;
    }
    days[dayIdx] = day;
    await persist({ ...plan.data, plan: { ...plan.data.plan, days } });
    setEditSlot(null);
  }

  async function onEstimate() {
    setBusy("estimate");
    setError(null);
    try {
      await estimateMealPlan(id);
      plan.reload();
      toast.success("Estimate updated.");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function onCreateGrocery() {
    setBusy("grocery");
    try {
      const gl = await createGroceryList(id);
      toast.success("Grocery list created.");
      navigate(`/grocery/${gl.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function onCopy() {
    if (!copyWeek) return setError("Choose the new week start date.");
    setCopying(true);
    try {
      const copy = await copyMealPlan(id, copyWeek);
      toast.success("Plan copied.");
      navigate(`/planner/${copy.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setCopying(false);
    }
  }

  async function onDelete() {
    try {
      await deleteMealPlan(id);
      toast.success("Plan deleted.");
      navigate("/planner");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setConfirmDelete(false);
    }
  }

  if (plan.error instanceof ApiError && plan.error.status === 404) {
    return (
      <EmptyState title="Plan not found" description="It may have been deleted."
        action={<Link to="/planner">Back to the planner</Link>} />
    );
  }
  if (plan.error) return <ErrorState error={plan.error} onRetry={plan.reload} />;
  if (!plan.data) return <Loading />;
  const p = plan.data;
  const estimateByDate = new Map<string, PlanEstimateDay>();
  for (const est of p.estimate?.days ?? []) {
    estimateByDate.set(est.day_date, est);
  }

  return (
    <>
      <PageHeader
        title={p.title}
        description={<>Week of {p.week_start_date} · source: {p.source} · revision {p.revision}</>}
        actions={<>
          <Link className="button-link secondary" to="/planner">Back</Link>
          <button type="button" className="secondary" onClick={() => setConfirmDelete(true)}>Delete</button>
        </>} />

      <Card title="Nutrition estimate" headingId="estimate-h">
        {!p.estimate ? (
          <>
            <p className="hint">
              Nutrition is only shown when every ingredient can be matched to a trusted food-composition
              source. Ingredients that cannot be matched are listed as missing, not estimated.
            </p>
            <button type="button" onClick={onEstimate} disabled={busy === "estimate"}>
              {busy === "estimate" ? "Estimating…" : "Estimate nutrition"}
            </button>
          </>
        ) : (
          <>
            <p className="small-text muted">{p.estimate.notes}</p>
            <p className="small-text">
              Estimated on{" "}
              <time dateTime={p.estimated_at ?? p.estimate.generated_at}>
                {p.estimated_at ?? p.estimate.generated_at}
              </time>
              {p.estimate.warnings.length > 0 && <> · {p.estimate.warnings.join(", ")}</>}
            </p>
            <ul className="plain-list small-text">
              {p.estimate.days.map((d) => (
                <li key={d.day_date}>
                  <strong>{dayLabel(d.day_date)}:</strong>{" "}
                  {d.kcal_low === d.kcal_high
                    ? `${Math.round(d.kcal_low)} kcal`
                    : `${Math.round(d.kcal_low)}–${Math.round(d.kcal_high)} kcal`}
                  {!d.complete && (
                    <span className="partial"> (missing: {d.missing_ingredients.join(", ")})</span>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <Card title="Copy to another week" headingId="copy-h">
        <div className="row wrap">
          <label htmlFor="copy-week" className="visually-hidden">New week start date</label>
          <input id="copy-week" type="date" value={copyWeek} onChange={(e) => setCopyWeek(e.target.value)} />
          <button type="button" className="secondary" onClick={onCopy} disabled={copying}>
            {copying ? "Copying…" : "Copy plan"}
          </button>
          <button type="button" className="secondary" onClick={onCreateGrocery}
            disabled={busy === "grocery"}>
            {busy === "grocery" ? "Creating…" : "Create grocery list"}
          </button>
        </div>
      </Card>

      <FormError message={error} />

      {p.plan.days.map((day, dayIdx) => (
        <PlanDayCard
          key={day.day_date}
          day={day}
          estimate={estimateByDate.get(day.day_date) ?? null}
          onAddMeal={() => setEditSlot({ dayIdx, mealIdx: null })}
          onEditMeal={(mealIdx) => setEditSlot({ dayIdx, mealIdx })}
        />
      ))}

      {editSlot && (
        <MealEditorDialog
          open
          day={p.plan.days[editSlot.dayIdx]}
          meal={editSlot.mealIdx !== null ? p.plan.days[editSlot.dayIdx].meals[editSlot.mealIdx] : null}
          onSave={(meal) => onMealSave(editSlot.dayIdx, editSlot.mealIdx, meal)}
          onDelete={
            editSlot.mealIdx !== null
              ? () => onMealSave(editSlot.dayIdx, editSlot.mealIdx, null)
              : undefined
          }
          onCancel={() => setEditSlot(null)}
        />
      )}

      <ConfirmDialog
        open={confirmDelete}
        title="Delete this plan?"
        message={`“${p.title}” and its estimate will be removed. Grocery lists derived from it are kept.`}
        confirmLabel="Delete"
        onConfirm={onDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </>
  );
}

// Suppress unused import warnings when CATEGORIES is only needed by subcomponents.
void CATEGORIES;