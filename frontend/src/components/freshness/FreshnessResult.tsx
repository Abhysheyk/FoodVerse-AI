import type { FreshnessDetail } from "../../api/types";
import { formatDate } from "../../lib/format";
import {
  ADVICE_CLASS, CERTAINTY_TEXT, LABEL_TONE, MATCH_TEXT, QUALITY_TEXT, SEVERITY_TEXT,
} from "../../lib/freshness";
import { Badge, Card } from "../ui";

function Detail({ label, value }: { label: string; value: string | null }) {
  return value ? <li><strong>{label}:</strong> {value}</li> : null;
}

/**
 * Two clearly separate parts: what the AI model reported seeing (observation), and guidance from
 * fixed rules (advice). The label describes one image and is never presented as a safety verdict.
 */
export function FreshnessResult({ detail }: { detail: FreshnessDetail }) {
  const r = detail.result;
  const f = r.findings;
  const a = r.advice;
  return (
    <>
      <Card title="Result for this image" headingId="result-heading">
        <p className="verdict-row">
          <Badge tone={LABEL_TONE[r.assessment.label]}>{r.assessment.label_text}</Badge>
          <span className="small-text muted">
            {f.analysed ? "about the photo only" : "the photo was not analysed"}
          </span>
        </p>
        <p className="alert info" role="note">{r.verdict_notice}</p>
        {r.assessment.inconclusive_reasons.length > 0 && (
          <>
            <h3>Why it is inconclusive</h3>
            <ul className="plain-list">
              {r.assessment.inconclusive_reasons.map((x) => <li key={x.code}>{x.text}</li>)}
            </ul>
          </>
        )}
      </Card>

      <Card title="What the image showed" headingId="seen-heading">
        <p className="source-tag">Reported by the AI model. This is observation, not advice, and it can be wrong.</p>
        {!f.analysed ? (
          <p>No image analysis was run, so nothing was observed.</p>
        ) : (
          <>
            <p className="small-text">
              Image quality: <strong>{QUALITY_TEXT[f.image_quality ?? ""] ?? f.image_quality}</strong>
              {f.matches_confirmed_food && <> · The image {MATCH_TEXT[f.matches_confirmed_food]}.</>}
              {f.food_visible === false && <> · The model did not see food.</>}
            </p>
            {f.observations.length > 0 ? (
              <ul className="observations">
                {f.observations.map((o, i) => (
                  <li key={`${o.feature}-${i}`}>
                    <p><strong>{o.feature_label}</strong>{o.location ? ` · ${o.location}` : ""}</p>
                    <p>{o.description}</p>
                    <p className="small-text muted">
                      {SEVERITY_TEXT[o.severity]} · {CERTAINTY_TEXT[o.certainty]} (the model’s own wording)
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p>
                The model did not report any visible changes in this image
                {r.assessment.label === "inconclusive" ? ", but the image was not good enough to rely on that" : ""}.
              </p>
            )}
            {f.limitations.length > 0 && (
              <>
                <h3>Limits of this image</h3>
                <ul className="plain-list">{f.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
              </>
            )}
            {f.notes && <p className="small-text">Model note: {f.notes}</p>}
            {f.withheld_text_count > 0 && (
              <p className="small-text muted">
                {f.withheld_text_count} model comment{f.withheld_text_count === 1 ? " was" : "s were"} withheld
                because {f.withheld_text_count === 1 ? "it" : "they"} contained a safety judgement, which this tool does not accept.
              </p>
            )}
          </>
        )}
      </Card>

      <Card title="Guidance" headingId="guidance-heading">
        <p className="source-tag">From fixed food-safety rules in this app. Not written by the AI model.</p>
        <div className={ADVICE_CLASS[a.level]} role="note">
          <p><strong>{a.headline}</strong></p>
        </div>
        {a.reasons.length > 0 && (
          <>
            <h3>Why</h3>
            <ul className="plain-list">{a.reasons.map((x) => <li key={x.code}>{x.text}</li>)}</ul>
          </>
        )}
        <h3>What to do</h3>
        <ul className="plain-list">{a.steps.map((s, i) => <li key={i}>{s}</li>)}</ul>
        {a.retake_tips.length > 0 && (
          <>
            <h3>To get a better photo</h3>
            <ul className="plain-list">{a.retake_tips.map((s, i) => <li key={i}>{s}</li>)}</ul>
          </>
        )}
        <h3>About {r.food.category_label.toLowerCase()}</h3>
        <ul className="plain-list">{a.category_cautions.map((s, i) => <li key={i}>{s}</li>)}</ul>
        <h3>Please remember</h3>
        <ul className="plain-list">{a.general_notes.map((s, i) => <li key={i}>{s}</li>)}</ul>
        <p className="small-text muted">
          General guidance based on commonly published advice; rules differ by country. Check official
          sources:{" "}
          {a.sources.map((s, i) => (
            <span key={s.url}>
              {i > 0 && " · "}
              <a href={s.url} target="_blank" rel="noopener noreferrer">{s.name}</a>
            </span>
          ))}
        </p>
      </Card>

      <Card title="Your details" headingId="details-heading">
        <ul className="plain-list">
          <Detail label="Food" value={`${r.food.name} (${r.food.category_label})`} />
          <Detail label="Stored" value={r.inputs.storage_condition.replace(/_/g, " ")} />
          <Detail label="Packaging" value={r.inputs.packaging.replace(/_/g, " ")} />
          <Detail label="Time stored" value={r.inputs.storage_hours === null ? null : `${r.inputs.storage_hours} hours`} />
          <Detail label="Bought" value={r.inputs.purchased_on} />
          <Detail label="Use-by date" value={r.inputs.use_by_date} />
          <Detail label="Best-before date" value={r.inputs.best_before_date} />
          <Detail label="Checked on" value={r.inputs.assessed_on} />
          <Detail label="Notes" value={r.inputs.notes} />
        </ul>
      </Card>

      <p className="small-text muted">
        {r.provider
          ? `Image analysed by the “${r.provider.model}” model (${r.provider.name}${r.provider.external ? ", external service" : ", on this server"}).`
          : "No AI model was used for this check."}{" "}
        Saved <time dateTime={r.generated_at}>{formatDate(r.generated_at)}</time>. No freshness score is
        calculated, and no trained freshness classifier is used.
      </p>
    </>
  );
}
