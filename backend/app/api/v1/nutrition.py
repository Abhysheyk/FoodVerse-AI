from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import AppSettings, CurrentUser, Nutrition
from app.core.errors import AppError
from app.core.limits import limiter
from app.nutrition.service import clean_query
from app.schemas.food import BarcodeResponse, NutritionSearchResponse
from app.services import food_service

router = APIRouter(prefix="/nutrition", tags=["nutrition"])


@router.get("/search", response_model=NutritionSearchResponse)
def search(
    user: CurrentUser,
    settings: AppSettings,
    nutrition: Nutrition,
    q: Annotated[str, Query(min_length=2, max_length=80)],
    limit: Annotated[int, Query(ge=1, le=15)] = 8,
) -> NutritionSearchResponse:
    """Find trusted nutrition records for a food name. Failing sources are reported, not hidden."""
    cleaned = clean_query(q)
    if len(cleaned) < 2:
        raise AppError("Enter at least two letters.", code="invalid_query", status_code=422)
    limiter("food search", settings.nutrition_search_rate_limit_per_minute).check(str(user.id))
    outcome = nutrition.search(cleaned, limit)
    return NutritionSearchResponse(
        query=cleaned,
        results=[food_service.candidate_out(settings, user, c) for c in outcome.results],
        sources=outcome.sources,
    )


@router.get("/barcode/{barcode}", response_model=BarcodeResponse)
def barcode(
    barcode: Annotated[str, Path(pattern=r"^\d{8,14}$")],
    user: CurrentUser,
    settings: AppSettings,
    nutrition: Nutrition,
) -> BarcodeResponse:
    limiter("food search", settings.nutrition_search_rate_limit_per_minute).check(str(user.id))
    found, sources = nutrition.barcode(barcode)
    return BarcodeResponse(
        barcode=barcode,
        result=food_service.candidate_out(settings, user, found) if found else None,
        sources=sources,
    )
