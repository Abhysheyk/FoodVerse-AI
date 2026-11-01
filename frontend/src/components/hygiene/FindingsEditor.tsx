import { useState } from "react";
import type { HygieneCertainty, HygieneFindingInput, HygieneSeverity } from "../../api/types";
import { CATEGORY_OPTIONS, CERTAINTY_LABELS, SEVERITY_LABELS } from "../../lib/hygiene";

export function FindingsEditor({
  findings, photos, onChange, onSave, onCancel, busy,
}: {
  findings: HygieneFindingInput[];
  photos: string[];
  onChange: (next: HygieneFindingInput[]) => void;
  onSave: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const [adding, setAdding] = useState(false);
  function update(i: number, patch: Partial<HygieneFindingInput>) {
    const next = [...findings]; next[i] = { ...next[i], ...patch }; onChange(next);
  }
  function remove(i: number) { onChange(findings.filter((_, j) => j !== i)); }
  return (
    <div>
      <ul className="item-list">
        {findings.map((f, i) => (
          <li key={f.finding_id ?? `new-${i}`} className="item-row">
            <div className="row wrap">
              <label className="visually-hidden" htmlFor={`f-cat-${i}`}>Category</label>
              <select id={`f-cat-${i}`} value={f.category} onChange={(e) => update(i, { category: e.target.value as HygieneFindingInput["category"] })}>
                {CATEGORY_OPTIONS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
              <label className="visually-hidden" htmlFor={`f-sev-${i}`}>Severity</label>
              <select id={`f-sev-${i}`} value={f.severity} onChange={(e) => update(i, { severity: e.target.value as HygieneSeverity })}>
                {(Object.keys(SEVERITY_LABELS) as HygieneSeverity[]).map((s) => <option key={s} value={s}>{SEVERITY_LABELS[s]}</option>)}
              </select>
              <label className="visually-hidden" htmlFor={`f-cer-${i}`}>Certainty</label>
              <select id={`f-cer-${i}`} value={f.certainty} onChange={(e) => update(i, { certainty: e.target.value as HygieneCertainty })}>
                {(Object.keys(CERTAINTY_LABELS) as HygieneCertainty[]).map((c) => <option key={c} value={c}>{CERTAINTY_LABELS[c]}</option>)}
              </select>
              <button type="button" className="secondary small" onClick={() => remove(i)}>Remove</button>
            </div>
            <label htmlFor={`f-desc-${i}`}>Description</label>
            <input id={`f-desc-${i}`} value={f.description} maxLength={400} onChange={(e) => update(i, { description: e.target.value })} />
            <label htmlFor={`f-loc-${i}`}>Where in the image</label>
            <input id={`f-loc-${i}`} value={f.location} maxLength={200} onChange={(e) => update(i, { location: e.target.value })} />
            {photos.length > 0 && (
              <>
                <label htmlFor={`f-photo-${i}`}>Evidence photo</label>
                <select id={`f-photo-${i}`} value={f.evidence_media_id ?? ""}
                  onChange={(e) => update(i, { evidence_media_id: e.target.value || null })}>
                  <option value="">No specific photo</option>
                  {photos.map((p, idx) => <option key={p} value={p}>Photo {idx + 1}</option>)}
                </select>
              </>
            )}
            <label htmlFor={`f-note-${i}`}>Your note (optional)</label>
            <input id={`f-note-${i}`} value={f.user_note ?? ""} maxLength={500} onChange={(e) => update(i, { user_note: e.target.value || null })} />
          </li>
        ))}
      </ul>
      <div className="row wrap">
        <button type="button" className="secondary" onClick={() => {
          setAdding(true);
          onChange([...findings, {
            source: "user", category: "surface_cleanliness", severity: "medium",
            description: "", location: "", certainty: "clearly_visible",
            evidence_media_id: null, user_note: null,
          }]);
        }} disabled={adding}>Add your own finding</button>
        <button type="button" onClick={onSave} disabled={busy}>{busy ? "Saving…" : "Save findings"}</button>
        <button type="button" className="secondary" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </div>
  );
}