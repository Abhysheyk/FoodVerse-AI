import { useCallback, useState } from "react";
import { deleteHistory, getModules, listHistory } from "../api/endpoints";
import type { HistoryItem, ModuleKey } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { errorMessage } from "../components/FormError";
import { HistoryList } from "../components/HistoryList";
import { useToast } from "../components/Toast";
import { EmptyState, ErrorState, Loading, PageHeader, Pagination } from "../components/ui";
import { useResource } from "../hooks/useResource";

export function HistoryPage() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [module, setModule] = useState<ModuleKey | "">("");
  const [pending, setPending] = useState<HistoryItem | null>(null);
  const modules = useResource(useCallback(() => getModules(), []));
  const history = useResource(useCallback(() => listHistory(page, module || null), [page, module]));
  const data = history.data;

  async function confirmDelete() {
    if (!pending) return;
    try {
      await deleteHistory(pending.id);
      toast.success("History entry deleted.");
      // If that was the last item on the page, step back one page.
      if (data && data.items.length === 1 && page > 1) setPage(page - 1);
      else history.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setPending(null);
    }
  }

  return (
    <>
      <PageHeader title="History" description="Everything you have analysed, newest first." />

      <div className="toolbar">
        <label htmlFor="module-filter">Module</label>
        <select id="module-filter" value={module}
          onChange={(e) => { setModule(e.target.value as ModuleKey | ""); setPage(1); }}>
          <option value="">All modules</option>
          {modules.data?.map((m) => <option key={m.key} value={m.key}>{m.title}</option>)}
        </select>
        {data && <span className="muted" aria-live="polite">{data.total} {data.total === 1 ? "entry" : "entries"}</span>}
      </div>

      {history.error ? (
        <ErrorState error={history.error} onRetry={history.reload} />
      ) : !data ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <EmptyState
          title={module ? "No entries for this module" : "No history yet"}
          description="Analyses will be listed here once analysis modules are released. Nothing is added automatically."
        />
      ) : (
        <>
          <HistoryList items={data.items} modules={modules.data ?? []} onDelete={setPending} />
          <Pagination page={data.page} pages={data.pages} onChange={setPage} />
        </>
      )}

      <ConfirmDialog
        open={pending !== null}
        title="Delete this entry?"
        message={`“${pending?.title ?? ""}” will be permanently removed from your history.`}
        confirmLabel="Delete"
        onConfirm={confirmDelete}
        onCancel={() => setPending(null)}
      />
    </>
  );
}
