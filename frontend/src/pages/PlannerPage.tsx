import { useCallback, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  createBlankPlan, deleteMealPlan, generateMealPlan, getPlanCapabilities, listMealPlans,
} from "../api/endpoints";
import { ApiError } from "../api/client";
import type { PlanSummary } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FormError, errorMessage } from "../components/FormError";
import { useToast } from "../components/Toast";
import { Badge, EmptyState, ErrorState, Loading, PageHeader, Pagination } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { mondayOf, toISODate } from "../lib/week";
import { formatDate } from "../lib/format";

export function PlannerPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [weekStart, setWeekStart] = useState(toISODate(mondayOf()));
  const [includeSnacks, setIncludeSnacks] = useState(true);
  const [busy, setBusy] = useState<"blank" | "ai" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<PlanSummary | null>(null);

  const caps = useResource(useCallback(() => getPlanCapabilities(), []));
  const plans = useResource(useCallback(() => listMealPlans(page), [page]));

  async function createBlank(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy("blank");
    try {
      const plan = await createBlankPlan(weekStart);
      toast.success("Blank plan created.");
      navigate(`/planner/${plan.id}`);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function generate() {
    setError(null);
    setBusy("ai");
    try {
      const plan = await generateMealPlan(weekStart, includeSnacks);
      toast.success("Plan generated.");
      navigate(`/planner/${plan.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "meal_plan_constraint_violation") {
        setError(
          "The generated plan broke a hard constraint (allergy, exclusion or dietary pattern). " +
            "Nothing was saved. Try again, or switch to a manual plan.",
        );
      } else {
        setError(errorMessage(err));
      }
    } finally {
      setBusy(null);
    }
  }

  async function confirmDelete() {
    if (!pending) return;
    try {
      await deleteMealPlan(pending.id);
      toast.success("Plan deleted.");
      if (plans.data && plans.data.items.length === 1 && page > 1) setPage(page - 1);
      else plans.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setPending(null);
    }
  }

  const data = plans.data;
  return (
    <>
      <PageHeader
        title="Meal planner"
        description="Plan breakfast, lunch, dinner and snacks for the week. Plans are drafts until you eat them; the meal log is the record of what you actually ate."
      />

      <form className="card" onSubmit={createBlank} aria-labelledby="new-plan-h">
        <h2 id="new-plan-h">New plan</h2>
        <label htmlFor="plan-week">Week starting (Monday)</label>
        <input id="plan-week" type="date" value={weekStart} onChange={(e) => setWeekStart(e.target.value)} />
        <label className="inline">
          <input type="checkbox" checked={includeSnacks}
            onChange={(e) => setIncludeSnacks(e.target.checked)} />
          Include snacks
        </label>

        {caps.error ? <ErrorState error={caps.error} onRetry={caps.reload} /> : null}
        {caps.data && !caps.data.text_provider_configured && (
          <p className="alert info" role="note">{caps.data.message}</p>
        )}
        {caps.data?.text_provider_external && (
          <p className="alert warn" role="note">
            The meal plan request (food names, quantities, allergies) will be sent to an external AI
            service ({caps.data.text_provider}).
          </p>
        )}
        <FormError message={error} />
        <div className="row wrap">
          <button type="submit" className="secondary" disabled={busy !== null}>
            {busy === "blank" ? "Creating…" : "Create blank plan"}
          </button>
          <button type="button" onClick={generate}
            disabled={busy !== null || !caps.data?.text_provider_configured}>
            {busy === "ai" ? "Generating…" : "Generate with AI"}
          </button>
          {caps.data && (
            <p className="hint">
              Allergies, exclusions and dietary pattern are enforced in code, not just in the prompt.
            </p>
          )}
        </div>
      </form>

      <h2 className="section-title">Your plans</h2>
      {plans.error ? (
        <ErrorState error={plans.error} onRetry={plans.reload} />
      ) : !data ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <EmptyState title="No plans yet" description="Create a blank plan or let the AI propose one." />
      ) : (
        <>
          <ul className="history-list">
            {data.items.map((p) => (
              <li key={p.id}>
                <div className="history-main">
                  <p className="history-title">
                    <Link to={`/planner/${p.id}`}>{p.title}</Link>
                  </p>
                  <p className="muted small-text">
                    Week of {p.week_start_date} · {p.day_count} days · {p.meal_count} meals ·{" "}
                    <time dateTime={p.updated_at}>{formatDate(p.updated_at)}</time>
                  </p>
                </div>
                <div className="history-side">
                  <Badge tone={p.source === "ai" ? "ok" : "neutral"}>{p.source}</Badge>
                  <button type="button" className="secondary small" onClick={() => setPending(p)}
                    aria-label={`Delete ${p.title}`}>Delete</button>
                </div>
              </li>
            ))}
          </ul>
          <Pagination page={data.page} pages={data.pages} onChange={setPage} />
        </>
      )}

      <ConfirmDialog open={pending !== null} title="Delete this plan?"
        message={`“${pending?.title ?? ""}” and its estimate will be deleted. Grocery lists derived from it are kept.`}
        confirmLabel="Delete" onConfirm={confirmDelete} onCancel={() => setPending(null)} />
    </>
  );
}