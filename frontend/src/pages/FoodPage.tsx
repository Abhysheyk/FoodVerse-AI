import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { getFoodCapabilities, scanPhoto, uploadPhotoWithProgress } from "../api/endpoints";
import type { ScanResponse } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { blankItem, draftFromObserved } from "../components/food/drafts";
import type { ItemDraft } from "../components/food/drafts";
import { MealBuilder } from "../components/food/MealBuilder";
import { FormError, errorMessage } from "../components/FormError";
import { Card, ErrorState, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { formatBytes } from "../lib/format";

const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];

type Phase =
  | { name: "pick" }
  | { name: "uploading"; progress: number }
  | { name: "scanning" }
  | { name: "build"; items: ItemDraft[]; scan: ScanResponse | null };

const isAbort = (err: unknown) => err instanceof DOMException && err.name === "AbortError";

export function FoodPage() {
  const caps = useResource(useCallback(() => getFoodCapabilities(), []));
  const [phase, setPhase] = useState<Phase>({ name: "pick" });
  const [photo, setPhotoState] = useState<{ file: File; url: string } | null>(null);
  const photoRef = useRef(photo);
  const [pickError, setPickError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const [uploadedId, setUploadedId] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const libraryRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);

  // The preview object URL is created in the event handler (not an effect) and revoked on replace/unmount.
  function setPhoto(next: File | null) {
    if (photoRef.current) URL.revokeObjectURL(photoRef.current.url);
    const value = next ? { file: next, url: URL.createObjectURL(next) } : null;
    photoRef.current = value;
    setPhotoState(value);
  }

  useEffect(
    () => () => {
      if (photoRef.current) URL.revokeObjectURL(photoRef.current.url);
      abortRef.current?.abort();
    },
    [],
  );

  function onPick(e: ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0] ?? null;
    e.target.value = ""; // allow re-picking the same file after removing it
    if (!picked) return;
    setPickError(null);
    setRunError(null);
    setUploadedId(null); // a new photo means a new upload
    // Fast feedback only. The server re-validates the real file content and is the authority.
    if (!ALLOWED_TYPES.includes(picked.type)) {
      setPhoto(null);
      setPickError("Choose a JPEG, PNG or WebP image.");
      return;
    }
    if (picked.size === 0) {
      setPhoto(null);
      setPickError("That file is empty.");
      return;
    }
    setPhoto(picked);
  }

  function removePhoto() {
    setPhoto(null);
    setUploadedId(null);
    setPickError(null);
    setRunError(null);
  }

  async function analyse() {
    const file = photo?.file;
    if (!file) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setRunError(null);
    try {
      let mediaId = uploadedId;
      if (!mediaId) {
        setPhase({ name: "uploading", progress: 0 });
        const media = await uploadPhotoWithProgress(file, (progress) => setPhase({ name: "uploading", progress }), controller.signal);
        mediaId = media.id;
        setUploadedId(mediaId);
      }
      setPhase({ name: "scanning" });
      const scan = await scanPhoto(mediaId, controller.signal);
      setPhase({ name: "build", items: scan.items.map(draftFromObserved), scan });
    } catch (err) {
      setPhase({ name: "pick" });
      if (!isAbort(err)) setRunError(errorMessage(err));
    } finally {
      abortRef.current = null;
    }
  }

  function startManual() {
    setPhase({ name: "build", items: [blankItem()], scan: null });
  }

  function reset() {
    setPhase({ name: "pick" });
    setPhoto(null);
    setUploadedId(null);
    setRunError(null);
    setPickError(null);
    setConfirmReset(false);
  }

  if (caps.error) return <ErrorState error={caps.error} onRetry={caps.reload} />;
  if (!caps.data) return <Loading />;
  const { vision, nutrition } = caps.data;

  if (phase.name === "build") {
    const scan = phase.scan;
    return (
      <>
        <PageHeader
          title="Check your meal"
          description="Confirm what is on the plate, add portions, and save it to your meal log."
          actions={<button type="button" className="secondary" onClick={() => setConfirmReset(true)}>Start over</button>}
        />
        {!nutrition.any_configured && (
          <p className="alert warn" role="note">
            No nutrition data source is set up on this server, so values cannot be calculated. See the setup
            notes (USDA_FDC_API_KEY, OPEN_FOOD_FACTS_ENABLED, or import a reference table).
          </p>
        )}
        <MealBuilder
          initialItems={phase.items}
          scan={scan ? {
            scanRef: scan.scan_ref, mediaId: scan.media_id, notes: scan.notes,
            uncertaintyNote: scan.uncertainty_note, model: scan.provider.model,
          } : null}
        />
        <ConfirmDialog open={confirmReset} title="Start over?"
          message="Your current foods and portions on this page will be discarded. Nothing has been saved yet."
          confirmLabel="Start over" onConfirm={reset} onCancel={() => setConfirmReset(false)} />
      </>
    );
  }

  const busy = phase.name === "uploading" || phase.name === "scanning";
  return (
    <>
      <PageHeader
        title="Analyse a meal"
        description="Photograph or upload your meal. A model suggests which foods it sees, you confirm them, and nutrition comes from trusted food-composition data."
      />

      {!vision.configured && (
        <p className="alert info" role="note">
          Photo recognition is not available: {vision.message ?? "no vision model is configured."} You can
          still enter foods yourself.
        </p>
      )}
      {vision.configured && vision.external && (
        <p className="alert warn" role="note">
          Your photo will be sent to an external service ({vision.provider}) that the server operator enabled.
        </p>
      )}

      <Card title="Photo" headingId="photo-heading">
        {photo ? (
          <figure className="preview">
            <img src={photo.url} alt="Preview of the selected meal photo" />
            <figcaption className="small-text muted">{photo.file.name} · {formatBytes(photo.file.size)}</figcaption>
          </figure>
        ) : (
          <p className="muted">No photo selected.</p>
        )}

        <div className="row wrap">
          <input ref={libraryRef} id="food-file" type="file" accept={ALLOWED_TYPES.join(",")} onChange={onPick}
            className="visually-hidden" aria-label="Choose a photo" disabled={busy} />
          <input ref={cameraRef} id="food-camera" type="file" accept="image/*" capture="environment" onChange={onPick}
            className="visually-hidden" aria-label="Take a photo" disabled={busy} />
          <button type="button" className="secondary" disabled={busy} onClick={() => libraryRef.current?.click()}>
            {photo ? "Replace photo" : "Choose a photo"}
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={() => cameraRef.current?.click()}>
            Take a photo
          </button>
          {photo && (
            <button type="button" className="secondary" disabled={busy} onClick={removePhoto}>Remove photo</button>
          )}
        </div>
        <p className="hint">JPEG, PNG or WebP. Photos are re-encoded, stored privately in your library, and
          analysed {vision.configured && !vision.external ? "on this server" : "only if a recognition model is set up"}.
          On a phone, “Take a photo” opens the camera; elsewhere it opens a file chooser.</p>

        <FormError message={pickError} />
        <FormError message={runError} />

        {phase.name === "uploading" && (
          <div role="status" aria-live="polite">
            <progress max={1} value={phase.progress} aria-label="Upload progress" />
            <p className="small-text">Uploading… {Math.round(phase.progress * 100)}%</p>
          </div>
        )}
        {phase.name === "scanning" && (
          <div className="loading" role="status" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <span>Analysing the photo. A local model on modest hardware can take a minute or more.</span>
          </div>
        )}

        <div className="row wrap">
          {busy ? (
            <button type="button" className="secondary" onClick={() => abortRef.current?.abort()}>Cancel</button>
          ) : (
            <button type="button" onClick={analyse} disabled={!photo || !vision.configured}>
              {runError && uploadedId ? "Try analysing again" : "Analyse photo"}
            </button>
          )}
          <button type="button" className="secondary" onClick={startManual} disabled={busy}>
            Enter foods without a photo
          </button>
        </div>
      </Card>
    </>
  );
}
