"""Hygiene inspection workflow.

The AI provider reports visible indicators only. Deterministic rules and fixed text own the
report's structure, actions, and disclosures. Failed or malformed model output never persists.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.ai.hygiene import (
    HYGIENE_JSON_SCHEMA,
    HygieneModelOutput,
    build_hygiene_prompt,
    parse_hygiene_output,
)
from app.ai.vision import VisionProvider
from app.core.config import Settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.limits import limiter
from app.domain import hygiene as rules
from app.models import (
    AnalysisRecord,
    AnalysisStatus,
    HygieneInspection,
    MediaKind,
    ModuleKey,
    User,
)
from app.repositories import hygiene as repo
from app.schemas.common import Page
from app.schemas.hygiene import (
    Choice,
    ChecklistItem,
    FindingInput,
    FindingOut,
    HygieneAudit,
    HygieneCapabilities,
    InspectionCreate,
    InspectionDetail,
    InspectionSummary,
    InspectionUpdate,
    LocationOut,
    StatusChange,
    category_label,
)
from app.services import food_service, media_service

logger = logging.getLogger("app.hygiene")
MAX_SCAN_IMAGE_BYTES = 16 * 1024 * 1024
MAX_PHOTOS_PER_INSPECTION = 8
MAX_FINDINGS = 80


# ---------------------------------------------------------------- capabilities
def capabilities(settings: Settings) -> HygieneCapabilities:
    return HygieneCapabilities(
        vision=food_service.vision_capability(settings),
        location_types=[Choice(value=k.value, label=v) for k, v in rules.LOCATION_TYPE_LABELS.items()],
        statuses=[Choice(value=k.value, label=v) for k, v in rules.STATUS_LABELS.items()],
        default_checklist=[ChecklistItem(**item) for item in rules.DEFAULT_CHECKLIST],
    )


# ---------------------------------------------------------------- helpers
def _invalid(message: str, code: str = "invalid_input") -> AppError:
    return AppError(message, code=code, status_code=422)


def _get_or_404(
    db: Session, user: User, inspection_id: uuid.UUID
) -> tuple[HygieneInspection, AnalysisRecord]:
    found = repo.get_owned(db, inspection_id, user.id)
    if found is None:
        raise NotFoundError("Inspection not found.", code="hygiene_inspection_not_found")
    return found


def _verify_media(db: Session, user: User, ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """Every photo must belong to the user and be an image. Order preserved."""
    seen: list[uuid.UUID] = []
    for mid in ids:
        asset = media_service.get_owned_or_404(db, user, mid)  # 404 for missing/foreign
        if asset.kind != MediaKind.IMAGE:
            raise _invalid("Only images can be attached to an inspection.", "invalid_item")
        if mid not in seen:
            seen.append(mid)
    return seen


def _read_photo(storage: Any, key: str) -> bytes:
    try:
        handle = storage.open(key)
    except Exception:
        raise AppError(
            "A stored photo is unavailable.", code="media_not_found", status_code=404
        ) from None
    with handle:
        data = handle.read(MAX_SCAN_IMAGE_BYTES + 1)
    if len(data) > MAX_SCAN_IMAGE_BYTES:
        raise _invalid("A photo is too large to analyse.", "invalid_item")
    return data


def _finding_out(f: FindingInput, source: str) -> FindingOut:
    return FindingOut(
        finding_id=f.finding_id or uuid.uuid4(),
        source=source,  # type: ignore[arg-type]
        category=f.category,
        category_label=category_label(f.category),
        severity=f.severity,
        severity_label=rules.SEVERITY_LABELS[f.severity],
        description=f.description,
        location=f.location,
        certainty=f.certainty,
        certainty_label=rules.CERTAINTY_LABELS[f.certainty],
        evidence_media_id=f.evidence_media_id,
        evidence_description=f.evidence_description,
        user_note=f.user_note,
        suggested_action=rules.CATEGORY_ACTIONS[f.category],
    )


def _build_findings(
    inputs: list[FindingInput], *, existing_by_id: dict[uuid.UUID, FindingOut]
) -> list[FindingOut]:
    """Preserve `model` provenance only when nothing about the finding changed.

    A finding that already exists (by `finding_id`) keeps `model` provenance when untouched;
    otherwise it becomes `user_edited`. New findings (no `finding_id`) are always `user` —
    clients cannot self-declare a finding as `model`; only the analysis path creates those.
    """
    out: list[FindingOut] = []
    for f in inputs:
        if f.finding_id and f.finding_id in existing_by_id:
            prev = existing_by_id[f.finding_id]
            unchanged = (
                prev.category == f.category
                and prev.severity == f.severity
                and prev.description == f.description
                and prev.location == f.location
                and prev.certainty == f.certainty
                and prev.evidence_media_id == f.evidence_media_id
                and prev.evidence_description == f.evidence_description
                and prev.user_note == f.user_note
            )
            source = "model" if prev.source == "model" and unchanged else "user_edited"
        else:
            source = "user"
        out.append(_finding_out(f, source))
    return out


def _checklist_or_default(items: list[ChecklistItem] | None) -> list[ChecklistItem]:
    if items is None:
        return [ChecklistItem(**d) for d in rules.DEFAULT_CHECKLIST]
    return items


def _summary_counts(findings: list[FindingOut]) -> tuple[int, str | None]:
    if not findings:
        return 0, None
    return len(findings), rules.highest_severity([f.severity.value for f in findings])


# ---------------------------------------------------------------- create / update
def create_inspection(
    db: Session, user: User, data: InspectionCreate
) -> InspectionDetail:
    if len(data.media_ids) > MAX_PHOTOS_PER_INSPECTION:
        raise _invalid(
            f"An inspection can include at most {MAX_PHOTOS_PER_INSPECTION} photos.",
            "too_many_photos",
        )
    media_ids = _verify_media(db, user, data.media_ids)
    now = datetime.now(UTC)
    loc = data.location_type
    findings: list[FindingOut] = []
    checklist = _checklist_or_default(None)
    audit = HygieneAudit(
        location=LocationOut(
            name=data.location_name,
            type=loc.value,
            type_label=rules.LOCATION_TYPE_LABELS[loc],
            area=data.area,
        ),
        checklist=checklist,
        findings=findings,
        notes=data.notes,
        disclosures=list(rules.DISCLOSURES),
        not_assessable=list(rules.NOT_ASSESSABLE),
        generated_at=now,
    )
    audit_dict = audit.model_dump(mode="json")
    audit_dict["media_ids"] = [str(m) for m in media_ids]
    record = AnalysisRecord(
        owner_id=user.id,
        module=ModuleKey.HYGIENE,
        status=AnalysisStatus.COMPLETED,
        title=f"Hygiene inspection: {data.location_name}"[:200],
        summary="Draft",
        result=audit_dict,
    )
    db.add(record)
    db.flush()
    row = HygieneInspection(
        analysis_id=record.id,
        owner_id=user.id,
        location_name=data.location_name,
        location_type=loc.value,
        area=data.area,
        status=rules.InspectionStatus.DRAFT.value,
        finding_count=0,
        highest_severity=None,
        photo_count=len(media_ids),
        revision=1,
    )
    db.add(row)
    db.commit()
    db.refresh(record)
    db.refresh(row)
    logger.info("hygiene_inspection_created user_id=%s id=%s", user.id, record.id)
    return _detail(row, record)


def update_inspection(
    db: Session,
    user: User,
    inspection_id: uuid.UUID,
    data: InspectionUpdate,
) -> InspectionDetail:
    row, record = _get_or_404(db, user, inspection_id)
    if row.status == rules.InspectionStatus.APPROVED.value:
        raise ConflictError("Approved inspections are read-only.", code="inspection_locked")
    if row.status == rules.InspectionStatus.IN_REVIEW.value and data.findings is not None:
        raise ConflictError(
            "Cannot edit findings while the inspection is in review.",
            code="inspection_in_review",
        )
    if data.expected_revision is not None and data.expected_revision != row.revision:
        raise ConflictError(
            "This inspection was changed somewhere else. Reload it and try again.",
            code="inspection_revision_conflict",
        )

    audit = dict(record.result or {})
    if data.media_ids is not None:
        media_ids = _verify_media(db, user, data.media_ids)
        audit["media_ids"] = [str(m) for m in media_ids]
        row.photo_count = len(media_ids)

    if (
        data.location_name is not None
        or data.location_type is not None
        or data.area is not None
    ):
        loc_name = data.location_name if data.location_name is not None else row.location_name
        loc_type = (
            data.location_type.value if data.location_type is not None else row.location_type
        )
        area = data.area if data.area is not None else row.area
        lt = rules.LocationType(loc_type)
        audit["location"] = {
            "name": loc_name,
            "type": lt.value,
            "type_label": rules.LOCATION_TYPE_LABELS[lt],
            "area": area,
        }
        row.location_name = loc_name
        row.location_type = lt.value
        row.area = area

    if data.notes is not None:
        audit["notes"] = data.notes or None

    if data.checklist is not None:
        audit["checklist"] = [c.model_dump() for c in data.checklist]

    if data.findings is not None:
        existing_by_id: dict[uuid.UUID, FindingOut] = {}
        for f in audit.get("findings", []):
            try:
                existing_by_id[uuid.UUID(f["finding_id"])] = FindingOut.model_validate(f)
            except (KeyError, ValueError):
                continue
        new_findings = _build_findings(data.findings, existing_by_id=existing_by_id)
        audit["findings"] = [f.model_dump(mode="json") for f in new_findings]
        row.finding_count, row.highest_severity = _summary_counts(new_findings)

    audit["generated_at"] = datetime.now(UTC).isoformat()
    record.result = audit
    row.revision += 1
    db.commit()
    db.refresh(record)
    db.refresh(row)
    logger.info(
        "hygiene_inspection_updated user_id=%s id=%s revision=%d",
        user.id, inspection_id, row.revision,
    )
    return _detail(row, record)


# ---------------------------------------------------------------- AI analysis
def analyze_inspection(
    db: Session,
    storage: Any,
    settings: Settings,
    user: User,
    inspection_id: uuid.UUID,
    make_provider: Any,
) -> InspectionDetail:
    row, record = _get_or_404(db, user, inspection_id)
    if row.status == rules.InspectionStatus.APPROVED.value:
        raise ConflictError("Approved inspections are read-only.", code="inspection_locked")

    audit = dict(record.result or {})
    media_ids = [uuid.UUID(str(m)) for m in audit.get("media_ids", [])]
    if not media_ids:
        raise _invalid("Add at least one photo before running the analysis.", "no_photos")

    limiter("photo analysis", settings.scan_rate_limit_per_minute).check(str(user.id))
    provider: VisionProvider = make_provider()
    prompt = build_hygiene_prompt(
        rules.LOCATION_TYPE_LABELS.get(
            rules.LocationType(row.location_type), "kitchen"
        ),
        row.area,
    )

    new_findings: list[FindingOut] = []
    all_limitations: list[str] = []
    model_notes_parts: list[str] = []
    total_withheld = 0
    now = datetime.now(UTC)

    for mid in media_ids:
        asset = media_service.get_owned_or_404(db, user, mid)
        if asset.kind != MediaKind.IMAGE:
            raise _invalid("Every photo must be an image.", "invalid_item")
        image = _read_photo(storage, asset.storage_key)
        logger.info(
            "hygiene_analysis_photo user_id=%s id=%s media_id=%s model=%s",
            user.id, inspection_id, mid, provider.info.model,
        )
        raw = provider.complete_json(image, prompt, HYGIENE_JSON_SCHEMA)
        output: HygieneModelOutput = parse_hygiene_output(raw)
        total_withheld += output.withheld_text_count
        for f in output.findings:
            cat = rules.FindingCategory(f.category)
            sev = rules.Severity(f.severity)
            cert = rules.Certainty(f.certainty)
            new_findings.append(
                FindingOut(
                    finding_id=uuid.uuid4(),
                    source="model",
                    category=cat,
                    category_label=category_label(cat),
                    severity=sev,
                    severity_label=rules.SEVERITY_LABELS[sev],
                    description=f.description,
                    location=f.location,
                    certainty=cert,
                    certainty_label=rules.CERTAINTY_LABELS[cert],
                    evidence_media_id=mid,
                    evidence_description=None,
                    user_note=None,
                    suggested_action=rules.CATEGORY_ACTIONS[cat],
                )
            )
        all_limitations.extend(output.limitations)
        if output.notes:
            model_notes_parts.append(output.notes)

    # Preserve existing user-added findings; model findings are replaced by the fresh analysis.
    existing = audit.get("findings", [])
    preserved = [
        FindingOut.model_validate(f)
        for f in existing
        if isinstance(f, dict) and f.get("source") == "user"
    ]
    final_findings = preserved + new_findings
    if len(final_findings) > MAX_FINDINGS:
        final_findings = final_findings[:MAX_FINDINGS]

    audit["findings"] = [f.model_dump(mode="json") for f in final_findings]
    audit["model_limitations"] = all_limitations[:12]
    audit["model_notes"] = (" ".join(model_notes_parts)[:500]) or None
    audit["withheld_text_count"] = total_withheld
    audit["provider"] = provider.info.model_dump()
    audit["analyzed_at"] = now.isoformat()
    audit["generated_at"] = now.isoformat()
    record.result = audit
    row.finding_count, row.highest_severity = _summary_counts(final_findings)
    row.revision += 1
    db.commit()
    db.refresh(record)
    db.refresh(row)
    logger.info(
        "hygiene_analysis_done user_id=%s id=%s photos=%d findings=%d",
        user.id, inspection_id, len(media_ids), len(new_findings),
    )
    return _detail(row, record)


# ---------------------------------------------------------------- status flow
def submit_inspection(db: Session, user: User, inspection_id: uuid.UUID) -> InspectionDetail:
    row, record = _get_or_404(db, user, inspection_id)
    if row.status not in (
        rules.InspectionStatus.DRAFT.value,
        rules.InspectionStatus.REJECTED.value,
    ):
        raise ConflictError(
            "Only a draft or rejected inspection can be submitted.", code="invalid_status"
        )
    if row.photo_count == 0:
        raise _invalid("Add at least one photo before submitting.", "no_photos")
    row.status = rules.InspectionStatus.IN_REVIEW.value
    db.commit()
    db.refresh(record)
    db.refresh(row)
    return _detail(row, record)


def approve_inspection(
    db: Session, user: User, inspection_id: uuid.UUID, data: StatusChange
) -> InspectionDetail:
    row, record = _get_or_404(db, user, inspection_id)
    if row.status != rules.InspectionStatus.IN_REVIEW.value:
        raise ConflictError(
            "Only an inspection in review can be approved.", code="invalid_status"
        )
    row.status = rules.InspectionStatus.APPROVED.value
    row.reviewed_at = datetime.now(UTC)
    if data.review_notes is not None:
        row.review_notes = data.review_notes
    db.commit()
    db.refresh(record)
    db.refresh(row)
    return _detail(row, record)


def reject_inspection(
    db: Session, user: User, inspection_id: uuid.UUID, data: StatusChange
) -> InspectionDetail:
    row, record = _get_or_404(db, user, inspection_id)
    if row.status != rules.InspectionStatus.IN_REVIEW.value:
        raise ConflictError(
            "Only an inspection in review can be rejected.", code="invalid_status"
        )
    if not data.review_notes:
        raise _invalid(
            "Rejecting requires review notes explaining what needs to change.",
            "review_notes_required",
        )
    row.status = rules.InspectionStatus.REJECTED.value
    row.review_notes = data.review_notes
    row.reviewed_at = datetime.now(UTC)
    db.commit()
    db.refresh(record)
    db.refresh(row)
    return _detail(row, record)


# ---------------------------------------------------------------- reads
def _summary(row: HygieneInspection, record: AnalysisRecord) -> InspectionSummary:
    try:
        lt = rules.LocationType(row.location_type)
    except ValueError:
        lt = rules.LocationType.OTHER
    try:
        st = rules.InspectionStatus(row.status)
    except ValueError:
        st = rules.InspectionStatus.DRAFT
    return InspectionSummary(
        id=row.analysis_id,
        location_name=row.location_name,
        location_type=lt.value,
        location_type_label=rules.LOCATION_TYPE_LABELS[lt],
        area=row.area,
        status=st,
        status_label=rules.STATUS_LABELS[st],
        finding_count=row.finding_count,
        highest_severity=row.highest_severity,
        photo_count=row.photo_count,
        revision=row.revision,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _detail(row: HygieneInspection, record: AnalysisRecord) -> InspectionDetail:
    audit_dict = record.result or {}
    media_ids = []
    for m in audit_dict.get("media_ids", []):
        try:
            media_ids.append(uuid.UUID(str(m)))
        except (ValueError, TypeError):
            continue
    findings_out: list[FindingOut] = []
    for f in audit_dict.get("findings", []):
        try:
            findings_out.append(FindingOut.model_validate(f))
        except Exception:
            continue
    audit_dict = {
        **audit_dict,
        "findings": [f.model_dump(mode="json") for f in findings_out],
        "disclosures": list(rules.DISCLOSURES),
        "not_assessable": list(rules.NOT_ASSESSABLE),
    }
    audit = HygieneAudit.model_validate(audit_dict)
    return InspectionDetail(
        **_summary(row, record).model_dump(),
        media_ids=media_ids,
        notes=(record.result or {}).get("notes"),
        review_notes=row.review_notes,
        result=audit,
    )


def get_inspection(db: Session, user: User, inspection_id: uuid.UUID) -> InspectionDetail:
    return _detail(*_get_or_404(db, user, inspection_id))


def list_inspections(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    status: rules.InspectionStatus | None,
    location_type: rules.LocationType | None,
) -> Page[InspectionSummary]:
    rows, total = repo.list_page(
        db,
        user.id,
        limit=page_size,
        offset=(page - 1) * page_size,
        status=status.value if status else None,
        location_type=location_type.value if location_type else None,
    )
    return Page.build([_summary(h, r) for h, r in rows], total, page, page_size)


def delete_inspection(db: Session, user: User, inspection_id: uuid.UUID) -> None:
    _, record = _get_or_404(db, user, inspection_id)
    db.delete(record)
    db.commit()
    logger.info("hygiene_inspection_deleted user_id=%s id=%s", user.id, inspection_id)


# ---------------------------------------------------------------- report
def _esc(value: str | None) -> str:
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def render_report_html(db: Session, user: User, inspection_id: uuid.UUID) -> str:
    """A self-contained HTML report. Print-to-PDF friendly. No external assets."""
    row, record = _get_or_404(db, user, inspection_id)
    d = _detail(row, record)
    checklist_rows = "".join(
        f"<tr><td>{'✔' if c.checked else '✗'}</td><td>{_esc(c.label)}</td>"
        f"<td>{_esc(c.note or '')}</td></tr>"
        for c in d.result.checklist
    ) or "<tr><td colspan='3'>No checklist recorded.</td></tr>"
    findings_rows = "".join(
        f"<tr>"
        f"<td>{_esc(f.category_label)}</td>"
        f"<td class='sev-{f.severity.value}'>{_esc(f.severity_label)}</td>"
        f"<td><strong>{_esc(f.description)}</strong>"
        + (f"<br/><span class='muted'>{_esc(f.location)}</span>" if f.location else "")
        + (
            f"<br/><span class='muted'>Evidence: {_esc(f.evidence_description)}</span>"
            if f.evidence_description
            else ""
        )
        + (
            f"<br/><span class='muted'>User note: {_esc(f.user_note)}</span>"
            if f.user_note
            else ""
        )
        + f"<br/><span class='source'>{_esc(f.source)}</span></td>"
        f"<td>{_esc(f.suggested_action)}</td>"
        f"</tr>"
        for f in d.result.findings
    ) or "<tr><td colspan='4'>No findings recorded.</td></tr>"
    disclosures = "".join(f"<li>{_esc(x)}</li>" for x in d.result.disclosures)
    not_assessable = "".join(f"<li>{_esc(x)}</li>" for x in d.result.not_assessable)
    generated = (
        d.result.generated_at.strftime("%Y-%m-%d %H:%M UTC")
        if d.result.generated_at
        else ""
    )
    reviewed = d.reviewed_at.strftime("%Y-%m-%d %H:%M UTC") if d.reviewed_at else "—"
    review_notes_html = (
        f"<p><strong>Review notes:</strong> {_esc(d.review_notes)}</p>"
        if d.review_notes
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Hygiene inspection — {_esc(d.location_name)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; color: #17261d;
         background: #fff; max-width: 900px; margin: 2rem auto; padding: 0 1rem; line-height: 1.5; }}
  h1, h2 {{ font-family: Georgia, serif; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 .5rem; }}
  h2 {{ font-size: 1.1rem; margin: 1.5rem 0 .5rem; border-bottom: 1px solid #d9d4c3; padding-bottom: .3rem; }}
  .meta {{ display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: .25rem 1.25rem; margin-bottom: 1rem; }}
  .meta dt {{ font-weight: 600; color: #526158; font-size: .9rem; }}
  .meta dd {{ margin: 0 0 .4rem; }}
  table {{ width: 100%; border-collapse: collapse; margin: .5rem 0; }}
  th, td {{ text-align: left; padding: .5rem .6rem; border-bottom: 1px solid #d9d4c3; vertical-align: top; }}
  th {{ background: #f6f3ea; font-weight: 600; font-size: .9rem; }}
  .sev-low {{ color: #1d6b43; }} .sev-medium {{ color: #b06a10; }} .sev-high {{ color: #a3261c; font-weight: 700; }}
  .source {{ font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; color: #526158; }}
  .muted {{ color: #526158; font-size: .9rem; }}
  .disclosure {{ background: #fcebcf; padding: .75rem 1rem; border-radius: 8px; margin: 1rem 0; }}
  .footer {{ margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #d9d4c3; font-size: .85rem; color: #526158; }}
  @media print {{ body {{ margin: 0; }} }}
</style></head>
<body>
<h1>Hygiene inspection report</h1>
<p><strong>{_esc(d.location_name)}</strong>{(' — ' + _esc(d.area)) if d.area else ''}
   <span class="muted">({_esc(d.location_type_label)})</span></p>
<dl class="meta">
  <dt>Status</dt><dd>{_esc(d.status_label)}</dd>
  <dt>Photos</dt><dd>{d.photo_count}</dd>
  <dt>Findings</dt><dd>{d.finding_count}{f' — highest severity: {_esc(d.highest_severity)}' if d.highest_severity else ''}</dd>
  <dt>Reviewed</dt><dd>{_esc(reviewed)}</dd>
  <dt>Generated</dt><dd>{_esc(generated)}</dd>
</dl>
{review_notes_html}
<h2>Checklist (self-reported)</h2>
<table><thead><tr><th></th><th>Item</th><th>Note</th></tr></thead><tbody>{checklist_rows}</tbody></table>
<h2>Findings</h2>
<table><thead><tr><th>Category</th><th>Severity</th><th>Description &amp; evidence</th><th>Suggested action</th></tr></thead>
<tbody>{findings_rows}</tbody></table>
<div class="disclosure"><strong>What this report cannot establish</strong><ul>{disclosures}</ul>
<strong>Not assessable from photos</strong><ul>{not_assessable}</ul></div>
<div class="footer">
  This report describes only visible conditions in the supplied photos. It is not an official
  inspection, and it does not verify compliance with any law, regulation, or food-safety standard.
  Reviewed by the account owner; the app does not perform face recognition or staff surveillance.
</div>
</body></html>"""