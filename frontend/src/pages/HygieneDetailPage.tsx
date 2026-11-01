import { useCallback, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  analyzeHygieneInspection, approveHygieneInspection, deleteHygieneInspection,
  fetchHygieneReportHtml, getHygieneInspection, rejectHygieneInspection,
  submitHygieneInspection, updateHygieneInspection,
} from "../api/endpoints";
import { ApiError } from "../api/client";
import type { HygieneFinding, HygieneFindingInput } from "../api/types";
import { AuthImage } from "../components/AuthImage";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FindingsEditor } from "../components/hygiene/FindingsEditor";
import { ChecklistEditor } from "../components/hygiene/ChecklistEditor";
import { errorMessage } from "../components/FormError";
import { useToast } from "../components/Toast";
import { Badge, Card, EmptyState, ErrorState, Loading, PageHeader } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { formatDate } from "../lib/format";
import { SEVERITY_TONE, SOURCE_LABEL, STATUS_TONE } from "../lib/hygiene";

export function HygieneDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<null | "delete" | "analyze" | "approve" | "submit">(null);
  const [rejectNotes, setRejectNotes] = useState("");
  const [showReject, setShowReject] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftFindings, setDraftFindings] = useState<HygieneFindingInput[]>([]);
  const inspection = useResource(useCallback(() => getHygieneInspection(id), [id]));

  const editable = inspection.data
    ? inspection.data.status === "draft" || inspection.data.status === "rejected"
    : false;

  function startEdit() {
    if (!inspection.data) return;
    setDraftFindings(inspection.data.result.findings.map((f) => ({
      finding_id: f.finding_id, source: f.source === "user" ? "user" : "model",
      category: f.category, severity: f.severity, description: f.description,
      location: f.location, certainty: f.certainty,
      evidence_media_id: f.evidence_media_id, evidence_description: f.evidence_description,
      user_note: f.user_note,
    })));
    setEditing(true);
  }

  async function saveEdits() {
    if (!inspection.data) return;
    setBusy("save");
    
    try {
      await updateHygieneInspection(inspection.data.id, {
        expected_revision: inspection.data.revision,
        findings: draftFindings,
      });
      setEditing(false);
      toast.success("Findings saved.");
      inspection.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    } 
  }

  async function runAnalysis() {
    setBusy("analyze");
    try {
      await analyzeHygieneInspection(id);
      toast.success("Analysis complete.");
      inspection.reload();
    } catch (err) { toast.error(errorMessage(err)); }
    finally { setBusy(null); setConfirm(null); }
  }

  async function submit() {
    setBusy("submit");
    try {
      await submitHygieneInspection(id);
      toast.success("Submitted for review.");
      inspection.reload();
    } catch (err) { toast.error(errorMessage(err)); }
    finally { setBusy(null); setConfirm(null); }
  }

  async function approve() {
    setBusy("approve");
    try {
      await approveHygieneInspection(id, null);
      toast.success("Approved.");
      inspection.reload();
    } catch (err) { toast.error(errorMessage(err)); }
    finally { setBusy(null); setConfirm(null); }
  }

  async function reject() {
    if (!rejectNotes.trim()) return toast.error("Add notes explaining what needs to change.");
    setBusy("reject");
    try {
      await rejectHygieneInspection(id, rejectNotes.trim());
      toast.success("Rejected; you can edit and resubmit.");
      setShowReject(false); setRejectNotes("");
      inspection.reload();
    } catch (err) { toast.error(errorMessage(err)); }
    finally { setBusy(null); }
  }

  async function remove() {
    try {
      await deleteHygieneInspection(id);
      toast.success("Inspection deleted.");
      navigate("/hygiene/history");
    } catch (err) { toast.error(errorMessage(err)); }
    finally { setConfirm(null); }
  }

  async function printReport() {
    try {
      const html = await fetchHygieneReportHtml(id);
      const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
      const w = window.open(url, "_blank", "noopener,noreferrer");
      if (!w) toast.error("Pop-up blocked. Allow pop-ups to open the report.");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) { toast.error(errorMessage(err)); }
  }

  if (inspection.error instanceof ApiError && inspection.error.status === 404) {
    return <EmptyState title="Inspection not found" description="It may have been deleted."
      action={<Link to="/hygiene/history">Back to inspections</Link>} />;
  }
  if (inspection.error) return <ErrorState error={inspection.error} onRetry={inspection.reload} />;
  if (!inspection.data) return <Loading />;
  const d = inspection.data;
  return (
    <>
      <PageHeader title={d.location_name}
        description={<>{d.location_type_label}{d.area ? ` · ${d.area}` : ""} · <time dateTime={d.created_at}>{formatDate(d.created_at)}</time></>}
        actions={
          <div className="row wrap">
            <button type="button" className="secondary small" onClick={printReport}>Print / Save PDF</button>
            {d.status !== "approved" && <button type="button" className="secondary small" onClick={() => setConfirm("delete")}>Delete</button>}
          </div>
        } />
      <p className="verdict-row"><Badge tone={STATUS_TONE[d.status]}>{d.status_label}</Badge>
        <span className="muted small-text">{d.photo_count} photo{d.photo_count === 1 ? "" : "s"} · {d.finding_count} finding{d.finding_count === 1 ? "" : "s"}{d.highest_severity ? ` · highest: ${d.highest_severity}` : ""}</span></p>

      {d.review_notes && (
        <p className="alert info" role="note"><strong>Review notes:</strong> {d.review_notes}</p>
      )}
      {d.notes && <Card title="Notes" headingId="n-h"><p>{d.notes}</p></Card>}

      <Card title="Photos" headingId="photos-h">
        <ul className="media-grid">
          {d.media_ids.map((m) => (
            <li key={m} className="media-card">
              <AuthImage mediaId={m} alt="Inspection photo" className="media-thumb" />
            </li>
          ))}
        </ul>
      </Card>

      <Card title="Checklist" headingId="check-h">
        <p className="source-tag">Self-reported by the inspector. Not verified from photos.</p>
        <ChecklistEditor value={d.result.checklist} disabled={true} onChange={() => {}} />
      </Card>

      <Card title="Findings" headingId="find-h">
        <p className="source-tag">Each finding names its source. AI observations describe visible conditions only.</p>
        {editable && !editing && (
          <div className="row wrap">
            <button type="button" onClick={() => setConfirm("analyze")} disabled={busy !== null || d.photo_count === 0}>
              {d.result.analyzed_at ? "Re-run analysis" : "Run AI analysis"}
            </button>
            <button type="button" className="secondary" onClick={startEdit} disabled={busy !== null}>Edit findings</button>
          </div>
        )}
        {editable && editing && (
          <FindingsEditor
            findings={draftFindings}
            photos={d.media_ids}
            onChange={setDraftFindings}
            onSave={saveEdits}
            onCancel={() => setEditing(false)}
            busy={busy === "save"}
          />
        )}
        {!editing && (
          d.result.findings.length === 0
            ? <EmptyState title="No findings recorded" description={editable ? "Run the analysis or add your own." : "Nothing was reported."} />
            : <FindingsReadOnly findings={d.result.findings} />
        )}
        {d.result.model_limitations.length > 0 && (
          <>
            <h3>What the model could not assess</h3>
            <ul className="plain-list">{d.result.model_limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
          </>
        )}
        {d.result.model_notes && <p className="small-text muted">Model note: {d.result.model_notes}</p>}
        {d.result.withheld_text_count > 0 && (
          <p className="small-text muted">
            {d.result.withheld_text_count} model comment{d.result.withheld_text_count === 1 ? " was" : "s were"} withheld because
            {d.result.withheld_text_count === 1 ? " it" : " they"} contained a compliance or safety verdict.
          </p>
        )}
      </Card>

      <Card title="What photos cannot establish" headingId="disc-h">
        <ul className="plain-list">{d.result.disclosures.map((x, i) => <li key={i}>{x}</li>)}</ul>
        <ul className="plain-list">{d.result.not_assessable.map((x, i) => <li key={i}>{x}</li>)}</ul>
      </Card>

      {editable && (
        <div className="stacked-actions">
          <button type="button" onClick={() => setConfirm("submit")} disabled={busy !== null || d.photo_count === 0}>
            Submit for review
          </button>
        </div>
      )}
      {d.status === "in_review" && (
        <div className="stacked-actions">
          <button type="button" onClick={() => setConfirm("approve")} disabled={busy !== null}>Approve</button>
          <button type="button" className="secondary" onClick={() => setShowReject(true)} disabled={busy !== null}>Reject…</button>
        </div>
      )}
      {d.status === "approved" && (
        <p className="small-text muted">Approved {d.reviewed_at ? <time dateTime={d.reviewed_at}>{formatDate(d.reviewed_at)}</time> : ""}. This record is now read-only.</p>
      )}

      {showReject && (
        <div className="overlay" role="dialog" aria-modal="true" aria-labelledby="rej-h">
          <div className="dialog">
            <h2 id="rej-h">Reject inspection?</h2>
            <p>Explain what needs to change. The inspector can edit and resubmit.</p>
            <label htmlFor="rej-notes">Reason</label>
            <textarea id="rej-notes" rows={3} maxLength={1000} value={rejectNotes} onChange={(e) => setRejectNotes(e.target.value)} />
            <div className="dialog-actions">
              <button type="button" className="secondary" onClick={() => setShowReject(false)}>Cancel</button>
              <button type="button" className="danger" onClick={reject} disabled={busy !== null}>{busy === "reject" ? "Rejecting…" : "Reject"}</button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog open={confirm === "delete"} title="Delete inspection?"
        message="The report and its findings will be permanently deleted." confirmLabel="Delete"
        onConfirm={remove} onCancel={() => setConfirm(null)} />
      <ConfirmDialog open={confirm === "analyze"} title="Run AI analysis?"
        message="The model will examine each photo. This can take a minute or more on modest hardware, and no compliance or safety verdict is ever produced."
        confirmLabel="Run analysis" onConfirm={runAnalysis} onCancel={() => setConfirm(null)} />
      <ConfirmDialog open={confirm === "submit"} title="Submit for review?"
        message="Findings will be locked while the inspection is in review." confirmLabel="Submit"
        onConfirm={submit} onCancel={() => setConfirm(null)} />
      <ConfirmDialog open={confirm === "approve"} title="Approve this inspection?"
        message="Approving makes the record read-only. It is a self-review; it does not certify compliance with any law or standard."
        confirmLabel="Approve" onConfirm={approve} onCancel={() => setConfirm(null)} />

      <p><Link to="/hygiene/history">← All inspections</Link></p>
    </>
  );
}

function FindingsReadOnly({ findings }: { findings: HygieneFinding[] }) {
  return (
    <ul className="observations">
      {findings.map((f) => (
        <li key={f.finding_id}>
          <p><strong>{f.category_label}</strong> · <Badge tone={SEVERITY_TONE[f.severity]}>{f.severity_label}</Badge>
            {" · "}<span className="muted small-text">{f.certainty_label} · {SOURCE_LABEL[f.source]}</span></p>
          <p>{f.description}{f.location ? ` (${f.location})` : ""}</p>
          {f.evidence_description && <p className="small-text muted">Evidence: {f.evidence_description}</p>}
          {f.user_note && <p className="small-text muted">Your note: {f.user_note}</p>}
          <p className="small-text"><strong>Suggested action:</strong> {f.suggested_action}</p>
        </li>
      ))}
    </ul>
  );
}
