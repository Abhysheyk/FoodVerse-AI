import { useCallback, useEffect, useRef, useState } from "react";
import { getFoodCapabilities, scanPhoto, uploadPhotoWithProgress } from "../api/endpoints";
import type { ScanResponse } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { blankItem, draftFromObserved } from "../components/food/drafts";
import type { ItemDraft } from "../components/food/drafts";
import { MealBuilder } from "../components/food/MealBuilder";
import { FormError, errorMessage } from "../components/FormError";
import { PhotoPicker } from "../components/PhotoPicker";
import { Card, ErrorState, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";

type Phase =
  | { name: "pick" }
  | { name: "uploading"; progress: number }
  | { name: "scanning" }
  | { name: "build"; items: ItemDraft[]; scan: ScanResponse | null };

const isAbort = (err: unknown) => err instanceof DOMException && err.name === "AbortError";

export function FoodPage() {
  const caps = useResource(useCallback(() => getFoodCapabilities(), []));
  const [phase, setPhase] = useState<Phase>({ name: "pick" });
  const [file, setFile] = useState<File | null>(null);
  const [pickerKey, setPickerKey] = useState(0); // bumping it resets the picker
  const [runError, setRunError] = useState<string | null>(null);
  const [uploadedId, setUploadedId] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  function onPhotoChange(next: File | null) {
    setFile(next);
    setRunError(null);
    setUploadedId(null); // a different photo means a new upload
  }

  async function analyse() {
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
    setFile(null);
    setPickerKey((k) => k + 1);
    setUploadedId(null);
    setRunError(null);
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
        <PhotoPicker key={pickerKey} onChange={onPhotoChange} disabled={busy}
          hint={<>JPEG, PNG or WebP. Photos are re-encoded, stored privately in your library, and
            analysed {vision.configured && !vision.external ? "on this server" : "only if a recognition model is set up"}.
            On a phone, “Take a photo” opens the camera; elsewhere it opens a file chooser.</>} />

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
            <button type="button" onClick={analyse} disabled={!file || !vision.configured}>
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
