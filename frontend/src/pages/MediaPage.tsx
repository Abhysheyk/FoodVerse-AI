import { useCallback, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { deleteMedia, getDashboardSummary, getMediaBlob, listMedia, uploadMedia } from "../api/endpoints";
import type { MediaItem } from "../api/types";
import { AuthImage } from "../components/AuthImage";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FormError, errorMessage } from "../components/FormError";
import { useToast } from "../components/Toast";
import { Card, EmptyState, ErrorState, Loading, PageHeader, Pagination } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { formatBytes, formatDate } from "../lib/format";

const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];

export function MediaPage() {
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [file, setFile] = useState<File | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [pending, setPending] = useState<MediaItem | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const summary = useResource(useCallback(() => getDashboardSummary(), []));
  const media = useResource(useCallback(() => listMedia(page), [page]));
  const maxBytes = summary.data?.media.max_upload_bytes;

  function onPick(e: ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0] ?? null;
    setFormError(null);
    setFile(null);
    if (!picked) return;
    // Quick feedback only. The server re-validates everything and is the authority.
    if (!ALLOWED_TYPES.includes(picked.type)) {
      setFormError("Choose a JPEG, PNG or WebP image.");
      return;
    }
    if (maxBytes && picked.size > maxBytes) {
      setFormError(`That file is ${formatBytes(picked.size)}. The limit is ${formatBytes(maxBytes)}.`);
      return;
    }
    setFile(picked);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setFormError(null);
    try {
      await uploadMedia(file);
      toast.success("Photo uploaded.");
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      if (page === 1) media.reload();
      else setPage(1);
      summary.reload();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  async function confirmDelete() {
    if (!pending) return;
    try {
      await deleteMedia(pending.id);
      toast.success("Photo deleted.");
      if (media.data && media.data.items.length === 1 && page > 1) setPage(page - 1);
      else media.reload();
      summary.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setPending(null);
    }
  }

  async function download(item: MediaItem) {
    try {
      const blob = await getMediaBlob(item.id, true);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = item.display_name;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const s = summary.data;
  const data = media.data;
  return (
    <>
      <PageHeader title="Media library" description="Photos you upload are private to your account." />

      <Card title="Upload a photo" headingId="upload-heading">
        <form onSubmit={onSubmit} noValidate>
          <label htmlFor="file">Image file</label>
          <input id="file" ref={inputRef} type="file" accept={ALLOWED_TYPES.join(",")} onChange={onPick}
            aria-describedby="file-help" />
          <p id="file-help" className="hint">
            JPEG, PNG or WebP{maxBytes ? `, up to ${formatBytes(maxBytes)}` : ""}. Images are re-encoded
            and location/camera metadata is removed.
          </p>
          <FormError message={formError} />
          <button type="submit" disabled={!file || uploading}>{uploading ? "Uploading…" : "Upload"}</button>
        </form>
        {s && (
          <div className="usage">
            <progress max={s.media.quota_bytes} value={s.media.total_bytes}
              aria-label="Storage used" />
            <p className="muted small-text">
              {formatBytes(s.media.total_bytes)} of {formatBytes(s.media.quota_bytes)} used
            </p>
          </div>
        )}
      </Card>

      <h2 className="section-title">Your photos</h2>
      {media.error ? (
        <ErrorState error={media.error} onRetry={media.reload} />
      ) : !data ? (
        <Loading />
      ) : data.items.length === 0 ? (
        <EmptyState title="No photos yet" description="Upload your first photo above." />
      ) : (
        <>
          <ul className="media-grid">
            {data.items.map((item) => (
              <li key={item.id} className="media-card">
                <AuthImage mediaId={item.id} alt={item.display_name} className="media-thumb" />
                <div className="media-meta">
                  <p className="media-name" title={item.display_name}>{item.display_name}</p>
                  <p className="muted small-text">
                    {item.width}×{item.height} · {formatBytes(item.size_bytes)}
                  </p>
                  <p className="muted small-text">{formatDate(item.created_at)}</p>
                </div>
                <div className="media-actions">
                  <button type="button" className="secondary small" onClick={() => download(item)}
                    aria-label={`Download ${item.display_name}`}>Download</button>
                  <button type="button" className="secondary small" onClick={() => setPending(item)}
                    aria-label={`Delete ${item.display_name}`}>Delete</button>
                </div>
              </li>
            ))}
          </ul>
          <Pagination page={data.page} pages={data.pages} onChange={setPage} />
        </>
      )}

      <ConfirmDialog
        open={pending !== null}
        title="Delete this photo?"
        message={`“${pending?.display_name ?? ""}” will be permanently deleted from your library.`}
        confirmLabel="Delete"
        onConfirm={confirmDelete}
        onCancel={() => setPending(null)}
      />
    </>
  );
}
