import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createFreshness, getFreshnessCapabilities, uploadPhotoWithProgress } from "../api/endpoints";
import { ApiError } from "../api/client";
import type { FreshnessRequest } from "../api/types";
import { FormError, errorMessage } from "../components/FormError";
import { PhotoPicker } from "../components/PhotoPicker";
import { useToast } from "../components/Toast";
import { Card, ErrorState, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { localDate } from "../lib/freshness";

type Phase = { name: "idle" } | { name: "uploading"; progress: number } | { name: "working"; analysing: boolean };

const isAbort = (err: unknown) => err instanceof DOMException && err.name === "AbortError";
// Provider-side problems: the user can still get guidance without image analysis.
const PROVIDER_TROUBLE = new Set([429, 502, 503, 504]);

export function FreshnessPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const caps = useResource(useCallback(() => getFreshnessCapabilities(), []));
  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const [file, setFile] = useState<File | null>(null);
  const [uploadedId, setUploadedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [offerGuidance, setOfferGuidance] = useState(false);
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [storage, setStorage] = useState("unknown");
  const [packaging, setPackaging] = useState("unknown");
  const [amount, setAmount] = useState("");
  const [unit, setUnit] = useState<"hours" | "days">("hours");
  const [purchased, setPurchased] = useState("");
  const [useBy, setUseBy] = useState("");
  const [bestBefore, setBestBefore] = useState("");
  const [notes, setNotes] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  function onPhotoChange(next: File | null) {
    setFile(next);
    setUploadedId(null);
    setError(null);
    setOfferGuidance(false);
  }

  function buildRequest(analyze: boolean, mediaId: string | null): FreshnessRequest | string {
    if (!name.trim()) return "Enter what food this is.";
    if (!category) return "Choose the type of food.";
    let storage_duration: FreshnessRequest["storage_duration"] = null;
    if (amount.trim() !== "") {
      const n = Number(amount);
      if (!Number.isInteger(n) || n < 0) return "Storage time must be a whole number, zero or more.";
      storage_duration = { amount: n, unit };
    }
    return {
      media_id: mediaId,
      analyze_image: analyze,
      food_name: name.trim(),
      food_category: category,
      storage_condition: storage,
      packaging,
      storage_duration,
      purchased_on: purchased || null,
      use_by_date: useBy || null,
      best_before_date: bestBefore || null,
      assessed_on: localDate(),
      notes: notes.trim() || null,
    };
  }

  async function submit(analyze: boolean) {
    setError(null);
    setOfferGuidance(false);
    if (analyze && !file) return setError("Choose or take a photo to analyse, or ask for guidance only.");
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      let mediaId = uploadedId;
      if (analyze && !mediaId && file) {
        const early = buildRequest(true, "pending");
        if (typeof early === "string") return setError(early); // validate before uploading anything
        setPhase({ name: "uploading", progress: 0 });
        const media = await uploadPhotoWithProgress(file, (progress) => setPhase({ name: "uploading", progress }), controller.signal);
        mediaId = media.id;
        setUploadedId(mediaId);
      }
      const body = buildRequest(analyze, mediaId);
      if (typeof body === "string") return setError(body);
      setPhase({ name: "working", analysing: analyze });
      const saved = await createFreshness(body, controller.signal);
      toast.success("Check saved.");
      navigate(`/freshness/${saved.id}`);
    } catch (err) {
      if (isAbort(err)) {
        setError("Stopped waiting. If the analysis had already finished, it will be in your past checks.");
      } else {
        setError(errorMessage(err));
        if (analyze && err instanceof ApiError && PROVIDER_TROUBLE.has(err.status)) setOfferGuidance(true);
      }
    } finally {
      abortRef.current = null;
      setPhase((p) => (p.name === "idle" ? p : { name: "idle" }));
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void submit(true);
  }

  if (caps.error) return <ErrorState error={caps.error} onRetry={caps.reload} />;
  if (!caps.data) return <Loading />;
  const { vision, categories, storage_conditions, packaging: packagingChoices } = caps.data;
  const busy = phase.name !== "idle";

  return (
    <>
      <PageHeader
        title="Freshness check"
        description="Describe the food and add a photo. You get what is visibly present in the image, plus food-safety guidance. It never tells you a food is safe."
        actions={<Link className="button-link secondary" to="/freshness/history">Past checks</Link>}
      />
      <p className="alert info" role="note">{caps.data.verdict_notice}</p>
      {!vision.configured && (
        <p className="alert info" role="note">
          Photo analysis is not available on this server: {vision.message ?? "no vision model is configured."} You
          can still get guidance from the details below.
        </p>
      )}
      {vision.configured && vision.external && (
        <p className="alert warn" role="note">
          Your photo will be sent to an external service ({vision.provider}) that the server operator enabled.
        </p>
      )}

      <form onSubmit={onSubmit} noValidate>
        <Card title="1. The food" headingId="food-heading">
          <label htmlFor="fresh-name">What food is it?</label>
          <input id="fresh-name" value={name} maxLength={80} onChange={(e) => setName(e.target.value)}
            placeholder="e.g. strawberries, leftover rice" />
          <label htmlFor="fresh-category">Type of food</label>
          <select id="fresh-category" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Choose…</option>
            {categories.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
          <p className="hint">You confirm the food; the model is only asked about what it can see.</p>
        </Card>

        <Card title="2. Photo" headingId="photo-heading">
          <PhotoPicker onChange={onPhotoChange} disabled={busy}
            hint="Use bright, even light and a sharp close-up. JPEG, PNG or WebP. Photos are stored privately in your library." />
        </Card>

        <Card title="3. Storage details (optional)" headingId="storage-heading">
          <p className="hint">These help the guidance. Leave anything you do not know.</p>
          <div className="field-row">
            <div>
              <label htmlFor="fresh-storage">Where was it kept?</label>
              <select id="fresh-storage" value={storage} onChange={(e) => setStorage(e.target.value)}>
                {storage_conditions.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="fresh-packaging">Packaging</label>
              <select id="fresh-packaging" value={packaging} onChange={(e) => setPackaging(e.target.value)}>
                {packagingChoices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
          </div>
          <label htmlFor="fresh-amount">How long has it been stored?</label>
          <div className="row">
            <input id="fresh-amount" inputMode="numeric" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="e.g. 3" />
            <select aria-label="Storage time unit" value={unit} onChange={(e) => setUnit(e.target.value as "hours" | "days")}>
              <option value="hours">hours</option>
              <option value="days">days</option>
            </select>
          </div>
          <div className="field-row">
            <div>
              <label htmlFor="fresh-bought">Bought on</label>
              <input id="fresh-bought" type="date" value={purchased} onChange={(e) => setPurchased(e.target.value)} />
            </div>
            <div>
              <label htmlFor="fresh-useby">Use-by date</label>
              <input id="fresh-useby" type="date" value={useBy} onChange={(e) => setUseBy(e.target.value)} />
            </div>
            <div>
              <label htmlFor="fresh-bb">Best-before date</label>
              <input id="fresh-bb" type="date" value={bestBefore} onChange={(e) => setBestBefore(e.target.value)} />
            </div>
          </div>
          <label htmlFor="fresh-notes">Notes (optional)</label>
          <textarea id="fresh-notes" rows={2} maxLength={500} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Card>

        <FormError message={error} />
        {phase.name === "uploading" && (
          <div role="status" aria-live="polite">
            <progress max={1} value={phase.progress} aria-label="Upload progress" />
            <p className="small-text">Uploading… {Math.round(phase.progress * 100)}%</p>
          </div>
        )}
        {phase.name === "working" && (
          <div className="loading" role="status" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <span>
              {phase.analysing
                ? "Looking at the photo. A local model on modest hardware can take a minute or more."
                : "Preparing guidance…"}
            </span>
          </div>
        )}
        {offerGuidance && (
          <p className="alert info" role="note">
            The photo could not be analysed right now. You can still get guidance based on your details; it will be
            clearly marked as not based on the image.
          </p>
        )}

        <div className="stacked-actions">
          {busy ? (
            <button type="button" className="secondary" onClick={() => abortRef.current?.abort()}>Cancel</button>
          ) : (
            <>
              <button type="submit" disabled={!file || !vision.configured}>Analyse photo</button>
              <button type="button" className={offerGuidance ? "" : "secondary"} onClick={() => void submit(false)}>
                Get guidance without analysing the photo
              </button>
            </>
          )}
        </div>
      </form>
    </>
  );
}
