import type { Calculation, ItemCalculation } from "../../api/types";
import { SUMMARY_WARNING_TEXT, WARNING_TEXT, formatAmount } from "../../lib/food";
import { Badge } from "../ui";

const ORIGIN: Record<ItemCalculation["origin"], string> = {
  model: "Suggested by the photo model, confirmed by you",
  model_edited: "Suggested by the photo model, renamed by you",
  user_added: "Added by you",
};

const CORE = ["energy_kcal", "protein_g", "carbs_g", "fat_g"];

function Totals({ calc }: { calc: Calculation }) {
  const rows = Object.values(calc.totals).filter((t) => CORE.includes(t.key) || t.low !== null);
  return (
    <table className="nutrient-table">
      <caption>Meal total</caption>
      <thead>
        <tr>
          <th scope="col">Nutrient</th>
          <th scope="col">Amount</th>
          <th scope="col">Coverage</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((t) => (
          <tr key={t.key}>
            <th scope="row">{t.label}</th>
            <td>
              {t.low === null || t.high === null ? (
                <span className="muted">Not available</span>
              ) : (
                <strong>{formatAmount(t.low, t.high, t.unit)}</strong>
              )}
            </td>
            <td className="small-text">
              {t.low === null ? (
                "No food reported this"
              ) : t.complete ? (
                "All foods included"
              ) : (
                <span className="partial">Partial: excludes {t.missing_items.join(", ")}</span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ItemResult({ item }: { item: ItemCalculation }) {
  const keys = Object.keys(item.nutrients);
  const shown = [...new Set([...CORE, ...keys])].filter((k) => CORE.includes(k) || keys.includes(k));
  const labelFor = (key: string) => key.replace(/_(kcal|g|mg)$/, "").replace(/_/g, " ");
  return (
    <article className="result-item">
      <header className="result-item-head">
        <h4>{item.name}</h4>
        <Badge>{ORIGIN[item.origin]}</Badge>
      </header>
      {item.food ? (
        <p className="small-text">
          Data: <strong>{item.food.name}</strong>
          {item.food.brand ? ` (${item.food.brand})` : ""} · {item.food.source_label} · ID {item.food.source_id}
          <br />
          <span className="muted">{item.food.attribution}</span>
        </p>
      ) : (
        <p className="small-text muted">No nutrition source chosen.</p>
      )}
      {item.portion && (
        <p className="small-text">
          Portion: {item.portion.description} ={" "}
          {formatAmount(item.portion.grams_low, item.portion.grams_high, "g")}{" "}
          {item.portion.uncertain && <Badge tone="warn">Estimate</Badge>}
        </p>
      )}
      {item.portion && item.food && (
        <table className="nutrient-table compact">
          <caption className="visually-hidden">Nutrients for {item.name}</caption>
          <tbody>
            {shown.map((k) => {
              const v = item.nutrients[k];
              return (
                <tr key={k}>
                  <th scope="row">{labelFor(k)}</th>
                  <td>{v ? formatAmount(v.low, v.high, v.unit) : <span className="muted">Not reported by source</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {item.warnings.length > 0 && (
        <ul className="plain-list small-text">
          {item.warnings.map((w) => (
            <li key={w}>{WARNING_TEXT[w] ?? w}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

/** Per-item and total estimates with their basis, sources and gaps. Pure display. */
export function NutritionResults({ calc }: { calc: Calculation }) {
  return (
    <div className="results">
      {calc.warnings.map((w) => (
        <p key={w} className="alert warn" role="note">
          {SUMMARY_WARNING_TEXT[w] ?? w}
        </p>
      ))}
      <Totals calc={calc} />
      <div className="result-items">
        {calc.items.map((item) => (
          <ItemResult key={item.item_id} item={item} />
        ))}
      </div>
      <p className="small-text muted">
        <strong>Basis:</strong> source values are {calc.unit_basis}. <strong>Method:</strong> {calc.method}.
      </p>
      <p className="small-text muted">{calc.disclaimer}</p>
    </div>
  );
}
