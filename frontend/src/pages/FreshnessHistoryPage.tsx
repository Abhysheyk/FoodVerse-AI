import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { deleteFreshness, listFreshness } from "../api/endpoints";
import type { FreshnessLabel, FreshnessSummary } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { errorMessage } from "../components/FormError";
import { useToast } from "../components/Toast";
import { Badge, EmptyState, ErrorState, Loading, PageHeader, Pagination } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { formatDate } from "../lib/format";
import { LABEL_FILTERS, LABEL_TONE } from "../lib/freshness";

export function FreshnessHistoryPage() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [label, setLabel] = useState<FreshnessLabel | "">("");
  const [pending, setPending] = useState<FreshnessSummary | null>(null);
  const list = useResource(useCallback(() => listFreshness(page, label || null), [page, label]));

  async function confirmDelete() {
    if (!pending) return;
    try {
      await deleteFreshness(pending.id);
      toast.success("Check deleted.");
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
      <PageHeader title="Past freshness checks" description="Each result describes one image on one day. It is not a safety record."
        actions={<Link className="button-link" to="/freshness">New check</Link>} />
      <div className="toolbar">
        <label htmlFor="fresh-filter">Result</label>
        <select id="fresh-filter" value={label} onChange={(e) => { setLabel(e.target.value as FreshnessLabel | ""); setPage(1); }}>
          <option value="">All results</option>
          {LABEL_FILTERS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
        </select>
      </div>
      {list.error ? (
        <ErrorState error={list.error} onRetry={list.reload} />
      ) : !data ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <EmptyState title={label ? "No checks with that result" : "No freshness checks yet"}
          description="Run a check and it will be saved here."
          action={<Link to="/freshness">Start a check</Link>} />
      ) : (
        <>
          <ul className="history-list">
            {data.items.map((c) => (
              <li key={c.id}>
                <div className="history-main">
                  <p className="history-title"><Link to={`/freshness/${c.id}`}>{c.food_name}</Link></p>
                  <p className="muted small-text">
                    {c.category_label} · <time dateTime={c.created_at}>{formatDate(c.created_at)}</time>
                    {c.image_analysed ? "" : " · photo not analysed"}
                  </p>
                </div>
                <div className="history-side">
                  <Badge tone={LABEL_TONE[c.label]}>{c.label_text}</Badge>
                  <button type="button" className="secondary small" onClick={() => setPending(c)}
                    aria-label={`Delete check for ${c.food_name}`}>Delete</button>
                </div>
              </li>
            ))}
          </ul>
          <Pagination page={data.page} pages={data.pages} onChange={setPage} />
        </>
      )}
      <ConfirmDialog open={pending !== null} title="Delete this check?"
        message={`The saved check for “${pending?.food_name ?? ""}” will be permanently deleted.`}
        confirmLabel="Delete" onConfirm={confirmDelete} onCancel={() => setPending(null)} />
    </>
  );
}
