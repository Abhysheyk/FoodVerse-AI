import { useCallback, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRecipe } from "../api/endpoints";
import { ApiError } from "../api/client";
import { RecipeView } from "../components/cooking/RecipeView";
import { EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";

export function RecipeDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const [servings, setServings] = useState<number | null>(null);
  const rec = useResource(useCallback(() => getRecipe(id, servings ?? undefined), [id, servings]));

  if (rec.error instanceof ApiError && rec.error.status === 404) {
    return <EmptyState title="Recipe not found" description="It may have been deleted."
      action={<Link to="/recipes">Back to saved recipes</Link>} />;
  }
  if (rec.error) return <ErrorState error={rec.error} onRetry={rec.reload} />;
  if (!rec.data) return <Loading />;
  const r = rec.data;
  return (
    <>
      <PageHeader title={r.title} description={r.description ?? undefined}
        actions={<>
          <Link className="button-link secondary" to="/recipes">All saved recipes</Link>
          {r.status === "saved" && (
            <button type="button" className="secondary" onClick={() => rec.reload()}>Refresh</button>
          )}
        </>} />
      <div className="toolbar">
        <label htmlFor="scale">Servings</label>
        <select id="scale" value={r.servings}
          onChange={(e) => setServings(Number(e.target.value))}>
          {[1, 2, 3, 4, 6, 8, 10, 12].map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
        <p className="small-text muted">Scaling changes quantities only; steps stay as written.</p>
      </div>
      <RecipeView recipe={r} onSaved={() => rec.reload()} onDeleted={() => rec.reload()} />
    </>
  );
}