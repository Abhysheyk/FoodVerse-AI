import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { deleteMeal, listMeals } from "../api/endpoints";
import type { MealCategory, MealSummary } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { errorMessage } from "../components/FormError";
import { useToast } from "../components/Toast";
import { Badge, Card, EmptyState, ErrorState, Loading, PageHeader, Pagination } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { CATEGORIES, categoryLabel, formatAmount } from "../lib/food";
import { formatDate } from "../lib/format";

export function caloriesText(c: MealSummary["calories"]): string {
  if (c.low === null || c.high === null) return "Calories not available";
  return `${formatAmount(c.low, c.high, "kcal")}${c.complete ? "" : " (partial)"}`;
}

export function MealsPage() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState<MealCategory | "">("");
  const [pending, setPending] = useState<MealSummary | null>(null);
  const meals = useResource(useCallback(() => listMeals(page, category || null), [page, category]));

  async function confirmDelete() {
    if (!pending) return;
    try {
      await deleteMeal(pending.id);
      toast.success("Meal deleted.");
      if (meals.data && meals.data.items.length === 1 && page > 1) setPage(page - 1);
      else meals.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setPending(null);
    }
  }

  const data = meals.data;
  return (
    <>
      <PageHeader title="Meal log" description="Meals you have analysed and saved."
        actions={<Link className="button-link" to="/food">Analyse a meal</Link>} />
      <div className="toolbar">
        <label htmlFor="meal-filter">Meal</label>
        <select id="meal-filter" value={category} onChange={(e) => { setCategory(e.target.value as MealCategory | ""); setPage(1); }}>
          <option value="">All meals</option>
          {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
      </div>
      {meals.error ? (
        <ErrorState error={meals.error} onRetry={meals.reload} />
      ) : !data ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <EmptyState title={category ? "No meals in this category" : "No meals saved yet"}
          description="Analyse a meal and save it, and it will appear here."
          action={<Link to="/food">Analyse a meal</Link>} />
      ) : (
        <>
          <ul className="history-list">
            {data.items.map((m) => (
              <li key={m.id}>
                <div className="history-main">
                  <p className="history-title"><Link to={`/meals/${m.id}`}>{m.items_label}</Link></p>
                  <p className="muted small-text">
                    {categoryLabel(m.category)} · <time dateTime={m.eaten_at}>{formatDate(m.eaten_at)}</time> · {m.item_count} item{m.item_count === 1 ? "" : "s"}
                  </p>
                  <p className="history-summary">{caloriesText(m.calories)}</p>
                </div>
                <div className="history-side">
                  <Badge>{categoryLabel(m.category)}</Badge>
                  <button type="button" className="secondary small" onClick={() => setPending(m)}
                    aria-label={`Delete ${m.items_label}`}>Delete</button>
                </div>
              </li>
            ))}
          </ul>
          <Pagination page={data.page} pages={data.pages} onChange={setPage} />
        </>
      )}
      <Card className="plain"><p className="small-text muted">Calorie figures are estimates from the portions and data sources you chose. “Partial” means some foods had no data.</p></Card>
      <ConfirmDialog open={pending !== null} title="Delete this meal?"
        message={`“${pending?.items_label ?? ""}” and its saved analysis will be permanently deleted.`}
        confirmLabel="Delete" onConfirm={confirmDelete} onCancel={() => setPending(null)} />
    </>
  );
}
