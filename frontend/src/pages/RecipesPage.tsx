import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { deleteRecipe, listRecipes } from "../api/endpoints";
import type { RecipeSummary } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { errorMessage } from "../components/FormError";
import { useToast } from "../components/Toast";
import { Badge, EmptyState, ErrorState, Loading, PageHeader, Pagination } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { formatDate } from "../lib/format";

export function RecipesPage() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [pendingQ, setPendingQ] = useState("");
  const [favorite, setFavorite] = useState<"" | "true" | "false">("");
  const [pending, setPending] = useState<RecipeSummary | null>(null);
  const list = useResource(useCallback(
    () => listRecipes(page, q || null, favorite === "" ? null : favorite === "true"),
    [page, q, favorite],
  ));

  function applyQuery() { setQ(pendingQ.trim()); setPage(1); }

  async function confirmDelete() {
    if (!pending) return;
    try {
      await deleteRecipe(pending.id);
      toast.success("Recipe deleted.");
      if (list.data && list.data.items.length === 1 && page > 1) setPage(page - 1);
      else list.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setPending(null);
    }
  }

  const data = list.data;
  return (
    <>
      <PageHeader title="Saved recipes" description="Everything the assistant has suggested that you kept."
        actions={<Link className="button-link" to="/cooking">Open cooking assistant</Link>} />
      <div className="toolbar">
        <label htmlFor="recipe-q">Search</label>
        <input id="recipe-q" value={pendingQ} onChange={(e) => setPendingQ(e.target.value)}
          placeholder="title or description" />
        <button type="button" className="secondary small" onClick={applyQuery}>Search</button>
        <label htmlFor="recipe-fav">Favorite</label>
        <select id="recipe-fav" value={favorite}
          onChange={(e) => { setFavorite(e.target.value as "" | "true" | "false"); setPage(1); }}>
          <option value="">All</option>
          <option value="true">Favorites</option>
          <option value="false">Not favorite</option>
        </select>
      </div>
      {list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : !data ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <EmptyState title={q ? "No recipes match that search" : "No saved recipes yet"}
          description={q ? "Try a different search term." : "Ask the assistant for a recipe and save it here."}
          action={<Link to="/cooking">Open cooking assistant</Link>} />
      ) : (
        <>
          <ul className="history-list">
            {data.items.map((r) => (
              <li key={r.id}>
                <div className="history-main">
                  <p className="history-title"><Link to={`/recipes/${r.id}`}>{r.title}</Link></p>
                  <p className="muted small-text">
                    Serves {r.servings}{r.total_minutes !== null ? ` · ${r.total_minutes} min` : ""} · {r.ingredient_count} ingredients
                    {r.dietary_tags.length > 0 ? ` · ${r.dietary_tags.join(", ")}` : ""}
                  </p>
                  <p className="muted small-text">Updated {formatDate(r.updated_at)}</p>
                </div>
                <div className="history-side">
                  {r.favorite && <Badge tone="warn">Favorite</Badge>}
                  <button type="button" className="secondary small" onClick={() => setPending(r)}
                    aria-label={`Delete ${r.title}`}>Delete</button>
                </div>
              </li>
            ))}
          </ul>
          <Pagination page={data.page} pages={data.pages} onChange={setPage} />
        </>
      )}
      <ConfirmDialog open={pending !== null} title="Delete this recipe?"
        message={`“${pending?.title ?? ""}” will be permanently deleted, including its history entry.`}
        confirmLabel="Delete" onConfirm={confirmDelete} onCancel={() => setPending(null)} />
    </>
  );
}