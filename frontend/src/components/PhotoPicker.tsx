import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";
import { FormError } from "./FormError";
import { formatBytes } from "../lib/format";

export const ALLOWED_PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];

/**
 * Choose, capture, preview, replace and remove one photo. Validation here is fast feedback only:
 * the server re-checks the real file content. Remount it (change `key`) to reset it.
 */
export function PhotoPicker({
  onChange,
  disabled = false,
  hint,
}: {
  onChange: (file: File | null) => void;
  disabled?: boolean;
  hint?: ReactNode;
}) {
  const [photo, setPhotoState] = useState<{ file: File; url: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const photoRef = useRef(photo);
  const libraryRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);

  // The preview object URL is created in the event handler (not an effect) and revoked on
  // replace/unmount.
  function setPhoto(next: File | null) {
    if (photoRef.current) URL.revokeObjectURL(photoRef.current.url);
    const value = next ? { file: next, url: URL.createObjectURL(next) } : null;
    photoRef.current = value;
    setPhotoState(value);
    onChange(next);
  }

  useEffect(
    () => () => {
      if (photoRef.current) URL.revokeObjectURL(photoRef.current.url);
    },
    [],
  );

  function onPick(e: ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files?.[0] ?? null;
    e.target.value = ""; // allow re-picking the same file after removing it
    if (!picked) return;
    setError(null);
    if (!ALLOWED_PHOTO_TYPES.includes(picked.type)) {
      setPhoto(null);
      setError("Choose a JPEG, PNG or WebP image.");
      return;
    }
    if (picked.size === 0) {
      setPhoto(null);
      setError("That file is empty.");
      return;
    }
    setPhoto(picked);
  }

  return (
    <div>
      {photo ? (
        <figure className="preview">
          <img src={photo.url} alt="Preview of the selected photo" />
          <figcaption className="small-text muted">
            {photo.file.name} · {formatBytes(photo.file.size)}
          </figcaption>
        </figure>
      ) : (
        <p className="muted">No photo selected.</p>
      )}
      <div className="row wrap">
        <input ref={libraryRef} type="file" accept={ALLOWED_PHOTO_TYPES.join(",")} onChange={onPick}
          className="visually-hidden" aria-label="Choose a photo" disabled={disabled} />
        <input ref={cameraRef} type="file" accept="image/*" capture="environment" onChange={onPick}
          className="visually-hidden" aria-label="Take a photo" disabled={disabled} />
        <button type="button" className="secondary" disabled={disabled} onClick={() => libraryRef.current?.click()}>
          {photo ? "Replace photo" : "Choose a photo"}
        </button>
        <button type="button" className="secondary" disabled={disabled} onClick={() => cameraRef.current?.click()}>
          Take a photo
        </button>
        {photo && (
          <button type="button" className="secondary" disabled={disabled}
            onClick={() => { setError(null); setPhoto(null); }}>
            Remove photo
          </button>
        )}
      </div>
      {hint && <p className="hint">{hint}</p>}
      <FormError message={error} />
    </div>
  );
}
