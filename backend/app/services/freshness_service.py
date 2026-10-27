"""Freshness / spoilage-sign assessment.

Trust boundaries, in order:
  1. The vision model reports only visible *evidence* (schema-validated; verdict language is
     withheld). It never chooses the label, the advice, or any risk statement.
  2. `app.domain.freshness.assess` derives the label and the guidance with fixed rules, from that
     evidence plus the details the user entered.
  3. Everything is saved as an audit record. No failed or partial model output is ever stored.
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.ai.freshness import (
    FRESHNESS_JSON_SCHEMA,
    FreshnessModelOutput,
    build_freshness_prompt,
    parse_freshness_output,
)
from app.ai.vision import VisionProvider
from app.core.config import Settings
from app.core.errors import AppError, NotFoundError
from app.core.limits import limiter
from app.domain import freshness as rules
from app.media.storage import StorageBackend, StorageError
from app.models import (
    AnalysisRecord,
    AnalysisStatus,
    FreshnessAssessment,
    MediaKind,
    ModuleKey,
    User,
)
from app.repositories import freshness as repo
from app.schemas.common import Page
from app.schemas.freshness import (
    AdviceOut,
    AssessmentOut,
    AssessmentRequest,
    Choice,
    FoodOut,
    FreshnessAudit,
    FreshnessCapabilities,
    FreshnessDetail,
    FreshnessSummary,
    ImageFindings,
    InputsOut,
    ObservationView,
    ReasonOut,
    SourceLink,
)
from app.services import food_service, media_service

logger = logging.getLogger("app.freshness")

FEATURE_LABELS: dict[rules.Feature, str] = {
    rules.Feature.DISCOLORATION: "Discolouration",
    rules.Feature.BRUISING: "Bruising",
    rules.Feature.WILTING: "Wilting",
    rules.Feature.MOLD_LIKE_GROWTH: "Mould-like growth",
    rules.Feature.SURFACE_CHANGE: "Unusual surface change",
    rules.Feature.VISIBLE_DAMAGE: "Visible damage",
    rules.Feature.OTHER: "Other visible change",
}
STORAGE_LABELS: dict[rules.StorageCondition, str] = {
    rules.StorageCondition.REFRIGERATOR: "Refrigerator",
    rules.StorageCondition.FREEZER: "Freezer",
    rules.StorageCondition.ROOM_TEMPERATURE: "Room temperature",
    rules.StorageCondition.UNKNOWN: "Not sure",
}
PACKAGING_LABELS: dict[rules.Packaging, str] = {
    rules.Packaging.SEALED_UNOPENED: "Sealed, unopened",
    rules.Packaging.OPENED: "Opened",
    rules.Packaging.UNPACKAGED: "Not packaged",
    rules.Packaging.UNKNOWN: "Not sure",
}
HEADLINES: dict[rules.AdviceLevel, str] = {
    rules.AdviceLevel.DISCARD: "Discarding it is recommended",
    rules.AdviceLevel.CAUTION: "Use caution: appearance cannot confirm safety",
    rules.AdviceLevel.GENERAL: "Appearance cannot confirm safety",
}


def capabilities(settings: Settings) -> FreshnessCapabilities:
    return FreshnessCapabilities(
        vision=food_service.vision_capability(settings),
        categories=[
            Choice(value=c.value, label=rules.CATEGORY_LABELS[c]) for c in rules.FoodCategory
        ],
        storage_conditions=[Choice(value=c.value, label=STORAGE_LABELS[c]) for c in STORAGE_LABELS],
        packaging=[Choice(value=c.value, label=PACKAGING_LABELS[c]) for c in PACKAGING_LABELS],
    )


def _invalid(message: str, code: str = "invalid_input") -> AppError:
    return AppError(message, code=code, status_code=422)


def _resolve_dates(req: AssessmentRequest) -> date:
    today = datetime.now(UTC).date()
    assessed_on = req.assessed_on or today
    if abs((assessed_on - today).days) > 1:
        raise _invalid(
            "The date on your device looks wrong. Check it and try again.", "invalid_date"
        )
    if req.purchased_on is not None and req.purchased_on > assessed_on:
        raise _invalid("The purchase date cannot be in the future.", "invalid_date")
    return assessed_on


def _evidence(out: FreshnessModelOutput) -> rules.ImageEvidence:
    return rules.ImageEvidence(
        image_quality=out.image_quality,
        food_visible=out.food_visible,
        matches_confirmed_food=out.matches_confirmed_food,
        observations=tuple(
            rules.ObservedSign(o.feature, o.description, o.location, o.severity, o.certainty)
            for o in out.observations
        ),
    )


def _findings(out: FreshnessModelOutput | None) -> ImageFindings:
    if out is None:
        return ImageFindings(analysed=False)
    return ImageFindings(
        analysed=True,
        image_quality=out.image_quality.value,
        food_visible=out.food_visible,
        matches_confirmed_food=out.matches_confirmed_food,
        observations=[
            ObservationView(
                feature=o.feature.value,
                feature_label=FEATURE_LABELS[o.feature],
                description=o.description,
                location=o.location,
                severity=o.severity,
                certainty=o.certainty,
            )
            for o in out.observations
        ],
        limitations=out.limitations,
        notes=out.notes,
        withheld_text_count=out.withheld_text_count,
    )


def _read_image(db: Session, storage: StorageBackend, user: User, media_id: uuid.UUID) -> bytes:
    asset = media_service.get_owned_or_404(db, user, media_id)  # ownership first
    if asset.kind != MediaKind.IMAGE:
        raise _invalid("Only images can be analysed.", "invalid_item")
    try:
        handle = storage.open(asset.storage_key)
    except StorageError:
        raise AppError(
            "The photo file is unavailable.", code="media_not_found", status_code=404
        ) from None
    with handle:
        image = handle.read(food_service.MAX_SCAN_IMAGE_BYTES + 1)
    if len(image) > food_service.MAX_SCAN_IMAGE_BYTES:
        raise _invalid("That image is too large to analyse.", "invalid_item")
    return image


def create_assessment(
    db: Session,
    storage: StorageBackend,
    settings: Settings,
    user: User,
    req: AssessmentRequest,
    make_provider: Callable[[], VisionProvider],
) -> FreshnessDetail:
    assessed_on = _resolve_dates(req)
    category = req.food_category
    media_id = req.media_id
    image: bytes | None = None
    if media_id is not None:
        if req.analyze_image:
            limiter("photo analysis", settings.scan_rate_limit_per_minute).check(str(user.id))
            image = _read_image(db, storage, user, media_id)
        else:
            media_service.get_owned_or_404(db, user, media_id)  # attach only the user's own photo

    output: FreshnessModelOutput | None = None
    provider_info = None
    if req.analyze_image and image is not None:
        provider = make_provider()  # clear error if no vision model is configured
        logger.info("freshness_started user_id=%s model=%s", user.id, provider.info.model)
        prompt = build_freshness_prompt(req.food_name, rules.CATEGORY_LABELS[category])
        raw = provider.complete_json(image, prompt, FRESHNESS_JSON_SCHEMA)
        output = parse_freshness_output(raw)  # VisionBadOutputError -> 502, nothing is saved
        provider_info = provider.info

    ctx = rules.Context(
        category=category,
        storage=req.storage_condition,
        packaging=req.packaging,
        storage_hours=req.storage_duration.hours if req.storage_duration else None,
        use_by=req.use_by_date,
        best_before=req.best_before_date,
        assessed_on=assessed_on,
    )
    result = rules.assess(_evidence(output) if output else None, ctx)

    generated_at = datetime.now(UTC)
    audit = FreshnessAudit(
        food=FoodOut(
            name=req.food_name,
            category=category.value,
            category_label=rules.CATEGORY_LABELS[category],
        ),
        inputs=InputsOut(
            storage_condition=req.storage_condition.value,
            packaging=req.packaging.value,
            storage_hours=ctx.storage_hours,
            purchased_on=req.purchased_on,
            use_by_date=req.use_by_date,
            best_before_date=req.best_before_date,
            assessed_on=assessed_on,
            notes=req.notes,
        ),
        findings=_findings(output),
        assessment=AssessmentOut(
            label=result.label.value,
            label_text=rules.LABEL_TEXT[result.label],
            inconclusive_reasons=[
                ReasonOut(code=r.code, text=r.text) for r in result.inconclusive_reasons
            ],
        ),
        advice=AdviceOut(
            level=result.advice_level.value,
            headline=HEADLINES[result.advice_level],
            reasons=[ReasonOut(code=r.code, text=r.text) for r in result.advice_reasons],
            steps=list(result.steps),
            category_cautions=list(result.category_cautions),
            general_notes=list(rules.GENERAL_NOTES),
            retake_tips=list(result.retake_tips),
            sources=[SourceLink(name=n, url=u) for n, u in rules.GUIDANCE_SOURCES],
        ),
        provider=provider_info,
        generated_at=generated_at,
    )
    record = AnalysisRecord(
        owner_id=user.id,
        module=ModuleKey.FRESHNESS,
        status=AnalysisStatus.COMPLETED,
        title=f"Freshness check: {req.food_name}"[:200],
        summary=audit.assessment.label_text,
        result=audit.model_dump(mode="json"),
        media_id=media_id,
    )
    db.add(record)
    db.flush()
    row = FreshnessAssessment(
        analysis_id=record.id,
        owner_id=user.id,
        food_name=req.food_name,
        food_category=category.value,
        label=result.label.value,
        advice_level=result.advice_level.value,
        image_analysed=output is not None,
    )
    db.add(row)
    db.commit()
    db.refresh(record)
    db.refresh(row)
    logger.info(
        "freshness_saved user_id=%s id=%s label=%s analysed=%s",
        user.id,
        record.id,
        row.label,
        row.image_analysed,
    )
    return _detail(row, record)


def _summary(row: FreshnessAssessment, record: AnalysisRecord) -> FreshnessSummary:
    return FreshnessSummary(
        id=row.analysis_id,
        food_name=row.food_name,
        food_category=row.food_category,
        category_label=rules.CATEGORY_LABELS[rules.FoodCategory(row.food_category)],
        label=row.label,
        label_text=rules.LABEL_TEXT[rules.VisualLabel(row.label)],
        advice_level=row.advice_level,
        image_analysed=row.image_analysed,
        media_id=record.media_id,
        created_at=row.created_at,
    )


def _detail(row: FreshnessAssessment, record: AnalysisRecord) -> FreshnessDetail:
    return FreshnessDetail(
        **_summary(row, record).model_dump(), result=FreshnessAudit.model_validate(record.result)
    )


def _get_or_404(
    db: Session, user: User, assessment_id: uuid.UUID
) -> tuple[FreshnessAssessment, AnalysisRecord]:
    found = repo.get_owned(db, assessment_id, user.id)
    if found is None:
        raise NotFoundError("Freshness check not found.", code="freshness_not_found")
    return found


def get_assessment(db: Session, user: User, assessment_id: uuid.UUID) -> FreshnessDetail:
    return _detail(*_get_or_404(db, user, assessment_id))


def delete_assessment(db: Session, user: User, assessment_id: uuid.UUID) -> None:
    _, record = _get_or_404(db, user, assessment_id)
    db.delete(record)  # the freshness_assessments row goes with it (ON DELETE CASCADE)
    db.commit()
    logger.info("freshness_deleted user_id=%s id=%s", user.id, assessment_id)


def list_assessments(
    db: Session,
    user: User,
    *,
    page: int,
    page_size: int,
    label: rules.VisualLabel | None,
    category: rules.FoodCategory | None,
) -> Page[FreshnessSummary]:
    rows, total = repo.list_page(
        db,
        user.id,
        limit=page_size,
        offset=(page - 1) * page_size,
        label=label.value if label else None,
        category=category.value if category else None,
    )
    return Page.build([_summary(a, r) for a, r in rows], total, page, page_size)
