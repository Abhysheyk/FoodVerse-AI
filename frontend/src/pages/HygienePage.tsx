import { useCallback, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createHygieneInspection, getHygieneCapabilities, uploadPhotoWithProgress } from "../api/endpoints";
import type { HygieneLocationType } from "../api/types";
import { FormError, errorMessage } from "../components/FormError";
import { Card, ErrorState, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { ALLOWED_PHOTO_TYPES } from "../components/PhotoPicker";
import { formatBytes } from "../lib/format";

type PhotoDraft = { id: string; file: File; previewUrl: string };

let localKey = 0;
const nextKey = () => `p-${++localKey}`;

export function HygienePage() {
  const navigate = useNavigate();
  const caps = useResource(useCallback(() => getHygieneCapabilities(), []));
  const [photos, setPhotos] = useState<PhotoDraft[]>([]);
  const [name, setName] = useState("");
  const [type, setType] = useState<HygieneLocationType>("restaurant_kitchen");
  const [area, setArea] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<{ name: "idle" } | { name: "uploading"; progress: number; index: number } | { name: "creating" }>({ name: "idle" });

  function addFiles(files: FileList | null) {
    if (!files) return;
    setError(null);
    const next: PhotoDraft[] = [];
    for (const f of Array.from(files)) {
      if (!ALLOWED_PHOTO_TYPES.includes(f.type)) { setError("Only JPEG, PNG and WebP photos are accepted."); continue; }
      next.push({ id: nextKey(), file: f, previewUrl: URL.createObjectURL(f) });
    }
    setPhotos((prev) => [...prev, ...next].slice(0, caps.data?.max_photos ?? 8));
  }

  function removePhoto(id: string) {
    setPhotos((prev) => {
      const target = prev.find((p) => p.id === id);
      if (target) URL.revokeObjectURL(target.previewUrl);
      return prev.filter((p) => p.id !== id);
    });
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) return setError("Enter the kitchen or location name.");
    if (photos.length === 0) return setError("Add at least one photo.");
    const controller = new AbortController();
    try {
      const mediaIds: string[] = [];
      for (let i = 0; i < photos.length; i++) {
        setPhase({ name: "uploading", progress: 0, index: i });
        const media = await uploadPhotoWithProgress(photos[i].file, (progress) => setPhase({ name: "uploading", progress, index: i }), controller.signal);
        mediaIds.push(media.id);
      }
      setPhase({ name: "creating" });
      const inspection = await createHygieneInspection({
        location_name: name.trim(),
        location_type: type,
        area: area.trim() || null,
        media_ids: mediaIds,
        notes: notes.trim() || null,
      });
      photos.forEach((p) => URL.revokeObjectURL(p.previewUrl));
      navigate(`/hygiene/${inspection.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setPhase({ name: "idle" });
    }
  }

  if (caps.error) return <ErrorState error={caps.error} onRetry={caps.reload} />;
  if (!caps.data) return <Loading />;
  const { vision, location_types, max_photos } = caps.data;
  const busy = phase.name !== "idle";

  return (
    <>
      <PageHeader
        title="Kitchen hygiene inspection"
        description="Photograph a kitchen area and record visible hygiene concerns. Reports describe only what photos show — never safety, compliance, or pathogen absence."
        actions={<Link className="button-link secondary" to="/hygiene/history">Past inspections</Link>}
      />
      {!vision.configured && (
        <p className="alert info" role="note">
          Photo analysis is not available on this server: {vision.message ?? "no vision model is configured."} You can still
          record your own observations.
        </p>
      )}
      <form onSubmit={onSubmit} noValidate>
        <Card title="1. Where" headingId="where-h">
          <label htmlFor="loc-name">Kitchen or location name</label>
          <input id="loc-name" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} placeholder="e.g. Main street kitchen" />
          <label htmlFor="loc-type">Type of kitchen</label>
          <select id="loc-type" value={type} onChange={(e) => setType(e.target.value as HygieneLocationType)}>
            {location_types.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
          <label htmlFor="loc-area">Area (optional)</label>
          <input id="loc-area" value={area} maxLength={120} onChange={(e) => setArea(e.target.value)} placeholder="e.g. prep station, dishwashing" />
        </Card>

        <Card title={`2. Photos (up to ${max_photos})`} headingId="photos-h">
          <p className="hint">Bright, even light is best. Photos are stored privately to your account.</p>
          <input
            type="file" multiple accept={ALLOWED_PHOTO_TYPES.join(",")}
            onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }}
            aria-label="Add photos" disabled={busy || photos.length >= max_photos}
          />
          {photos.length > 0 && (
            <ul className="media-grid" style={{ marginTop: ".75rem" }}>
              {photos.map((p) => (
                <li key={p.id} className="media-card">
                  <img src={p.previewUrl} alt="" className="media-thumb" />
                  <div className="media-meta"><p className="media-name">{p.file.name}</p><p className="muted small-text">{formatBytes(p.file.size)}</p></div>
                  <div className="media-actions">
                    <button type="button" className="secondary small" onClick={() => removePhoto(p.id)} disabled={busy}>Remove</button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="3. Notes (optional)" headingId="notes-h">
          <textarea id="h-notes" rows={3} maxLength={2000} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Card>

        <FormError message={error} />
        {phase.name === "uploading" && (
          <div role="status" aria-live="polite">
            <progress max={1} value={phase.progress} aria-label="Upload progress" />
            <p className="small-text">Uploading photo {phase.index + 1} of {photos.length} — {Math.round(phase.progress * 100)}%</p>
          </div>
        )}
        {phase.name === "creating" && (
          <div className="loading" role="status"><span className="spinner" aria-hidden="true" />Saving…</div>
        )}
        <button type="submit" disabled={busy || photos.length === 0 || !name.trim()}>
          {busy ? "Creating…" : "Create draft inspection"}
        </button>
      </form>
    </>
  );
}