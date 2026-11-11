import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { deleteGroceryList, listGroceryLists } from "../api/endpoints";
import type { GroceryListSummary } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { errorMessage } from "../components/FormError";
import { useToast } from "../components/Toast";
import { Badge, EmptyState, ErrorState, Loading, PageHeader, Pagination } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { formatDate } from "../lib/format";

export function GroceryListsPage() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState<GroceryListSummary | null>(null);
  const lists = useResource(useCallback(() => listGroceryLists(page), [page]));

  async function confirmDelete() {
    if (!pending) return;
    try {
      await deleteGroceryList(pending.id);
      toast.success("Grocery list deleted.");
      if (lists.data && lists.data.items.length === 1 && page > 1) setPage(page - 1);
      else lists.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setPending(null);
    }
  }

  const data = lists.data;
  return (
    <>
      <PageHeader title="Grocery lists" description="Bundled from a meal plan. Item quantity edits are saved." />
      {lists.error ? (
        <ErrorState error={lists.error} onRetry={lists.reload} />
      ) : !data ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <EmptyState title="No grocery lists yet"
          description="Open a meal plan and choose “Create grocery list”." />
      ) : (
        <>
          <ul className="history-list">
            {data.items.map((gl) => (
              <li key={gl.id}>
                <div className="history-main">
                  <p className="history-title"><Link to={`/grocery/${gl.id}`}>{gl.title}</Link></p>
                  <p className="muted small-text">
                    {gl.item_count} item{gl.item_count === 1 ? "" : "s"} ·{" "}
                    {gl.checked_count} checked · <time dateTime={gl.updated_at}>{formatDate(gl.updated_at)}</time>
                  </p>
                </div>
                <div className="history-side">
                  <Badge>{gl.checked_count}/{gl.item_count}</Badge>
                  <button type="button" className="secondary small"
                    onClick={() => setPending(gl)}
                    aria-label={`Delete ${gl.title}`}>Delete</button>
                </div>
              </li>
            ))}
          </ul>
          <Pagination page={data.page} pages={data.pages} onChange={setPage} />
        </>
      )}
      <ConfirmDialog open={pending !== null} title="Delete this grocery list?"
        message={`“${pending?.title ?? ""}” will be deleted. The meal plan it was derived from is kept.`}
        confirmLabel="Delete" onConfirm={confirmDelete} onCancel={() => setPending(null)} />
    </>
  );
}