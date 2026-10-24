import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";

interface Props {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  /** Runs when confirmed. The dialog stays open (and disabled) until it settles. */
  onConfirm: () => Promise<void> | void;
  onCancel: () => void;
}

/**
 * Accessible modal confirmation: focus moves to the safe (Cancel) button, Tab is trapped,
 * Escape cancels, and focus returns to whatever opened it.
 */
export function ConfirmDialog({ open, title, message, confirmLabel, onConfirm, onCancel }: Props) {
  const titleId = useId();
  const descId = useId();
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();
    return () => opener?.focus?.();
  }, [open]);

  if (!open) return null;

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "Escape" && !busy) {
      e.stopPropagation();
      onCancel();
      return;
    }
    if (e.key !== "Tab") return;
    const focusable = dialogRef.current?.querySelectorAll<HTMLElement>("button:not([disabled])");
    if (!focusable || focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  async function confirm() {
    setBusy(true);
    try {
      await onConfirm();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && !busy && onCancel()}>
      <div ref={dialogRef} className="dialog" role="dialog" aria-modal="true"
        aria-labelledby={titleId} aria-describedby={descId} onKeyDown={onKeyDown}>
        <h2 id={titleId}>{title}</h2>
        <p id={descId}>{message}</p>
        <div className="dialog-actions">
          <button ref={cancelRef} type="button" className="secondary" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="danger" onClick={confirm} disabled={busy}>
            {busy ? "Working…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
