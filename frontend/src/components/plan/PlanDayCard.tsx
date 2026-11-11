import type { PlanDay, PlanEstimateDay, PlanMeal } from "../../api/types";
import { dayLabel } from "../../lib/week";
import { Badge } from "../ui";

export function PlanDayCard({
  day, estimate, onAddMeal, onEditMeal,
}: {
  day: PlanDay;
  estimate: PlanEstimateDay | null;
  onAddMeal: () => void;
  onEditMeal: (mealIdx: number) => void;
}) {
  const kcalText =
    estimate && estimate.kcal_low === estimate.kcal_high
      ? `${Math.round(estimate.kcal_low)} kcal`
      : estimate
        ? `${Math.round(estimate.kcal_low)}–${Math.round(estimate.kcal_high)} kcal`
        : null;
  return (
    <section className="card" aria-labelledby={`day-${day.day_date}`}>
      <div className="page-header" style={{ marginBottom: "0.5rem" }}>
        <div>
          <h2 id={`day-${day.day_date}`}>{dayLabel(day.day_date)}</h2>
          <p className="muted small-text">
            {day.meals.length} meal{day.meals.length === 1 ? "" : "s"}
            {kcalText && <> · <strong>{kcalText}</strong>{!estimate?.complete && " (partial)"}</>}
          </p>
        </div>
        <button type="button" className="secondary small" onClick={onAddMeal}>Add meal</button>
      </div>
      {day.meals.length === 0 ? (
        <p className="muted">No meals planned for this day yet.</p>
      ) : (
        <ul className="item-list" style={{ margin: 0 }}>
          {day.meals.map((meal, idx) => (
            <PlanMealRow
              key={`${meal.meal}-${idx}`}
              meal={meal}
              estimate={estimate?.meals.find((m) => m.meal === meal.meal) ?? null}
              onEdit={() => onEditMeal(idx)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function PlanMealRow({
  meal, estimate, onEdit,
}: {
  meal: PlanMeal;
  estimate: PlanEstimateDay["meals"][number] | null;
  onEdit: () => void;
}) {
  const kcal =
    estimate && estimate.kcal_low === estimate.kcal_high
      ? `${Math.round(estimate.kcal_low)} kcal`
      : estimate
        ? `${Math.round(estimate.kcal_low)}–${Math.round(estimate.kcal_high)} kcal`
        : null;
  return (
    <li className="item-row">
      <div className="result-item-head">
        <div>
          <p className="small-text muted" style={{ margin: 0, textTransform: "capitalize" }}>
            {meal.meal}
          </p>
          <h3 style={{ margin: 0 }}>{meal.title || "(untitled meal)"}</h3>
        </div>
        <div style={{ display: "flex", gap: ".5rem", alignItems: "center" }}>
          <Badge>{meal.servings} serving{meal.servings === 1 ? "" : "s"}</Badge>
          {meal.cooking_minutes && <Badge tone="neutral">{meal.cooking_minutes} min</Badge>}
          {kcal && <Badge tone={estimate?.complete ? "ok" : "warn"}>{kcal}</Badge>}
          <button type="button" className="secondary small" onClick={onEdit}>Edit</button>
        </div>
      </div>
      {meal.ingredients.length > 0 && (
        <p className="small-text muted">
          {meal.ingredients
            .map((i) => `${i.quantity} ${i.unit} ${i.name}`)
            .join(" · ")}
        </p>
      )}
      {meal.notes && <p className="small-text">{meal.notes}</p>}
    </li>
  );
}