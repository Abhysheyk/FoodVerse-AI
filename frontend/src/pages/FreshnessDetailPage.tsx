import { useCallback, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { deleteFreshness, getFreshness } from "../api/endpoints";
import { ApiError } from "../api/client";
import { AuthImage } from "../components/AuthImage";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FreshnessResult } from "../components/freshness/FreshnessResult";
import { errorMessage } from "../components/FormError";
import { useToast } from "../components/Toast";
import { Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { formatDate } from "../lib/format";

export function FreshnessDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  const check = useResource(useCallback(() => getFreshness(id), [id]));

  async function remove() {
    try {
      await deleteFreshness(id);
      toast.success("Check deleted.");
      navigate("/freshness/history");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setConfirming(false);
    }
  }

  if (check.error instanceof ApiError && check.error.status === 404) {
    return <EmptyState title="Check not found" description="It may have been deleted."
      action={<Link to="/freshness/history">Back to past checks</Link>} />;
  }
  if (check.error) return <ErrorState error={check.error} onRetry={check.reload} />;
  if (!check.data) return <Loading />;
  const d = check.data;
  return (
    <>
      <PageHeader title={d.food_name}
        description={<>{d.category_label} · <time dateTime={d.created_at}>{formatDate(d.created_at)}</time></>}
        actions={<>
          <Link className="button-link secondary" to="/freshness">New check</Link>
          <button type="button" className="secondary" onClick={() => setConfirming(true)}>Delete</button>
        </>} />
      {d.media_id && (
        <Card title="Photo" headingId="photo-h">
          <AuthImage mediaId={d.media_id} alt={`Photo of ${d.food_name}`} className="detail-photo" />
        </Card>
      )}
      <FreshnessResult detail={d} />
      <p><Link to="/freshness/history">← Past checks</Link></p>
      <ConfirmDialog open={confirming} title="Delete this check?"
        message="This check and its saved result will be permanently deleted."
        confirmLabel="Delete" onConfirm={remove} onCancel={() => setConfirming(false)} />
    </>
  );
}
