from fastapi import APIRouter, Depends

from app.api.deps import (
    AppSettings,
    CurrentUser,
    DbSession,
    Nutrition,
    Storage,
    VisionFactory,
    require_csrf_header,
)
from app.schemas.food import (
    CalculateRequest,
    CalculationOut,
    FoodCapabilities,
    ScanRequest,
    ScanResponse,
)
from app.services import food_service, meal_service

router = APIRouter(prefix="/food", tags=["food"])


@router.get("/capabilities", response_model=FoodCapabilities)
def capabilities(
    _user: CurrentUser, settings: AppSettings, nutrition: Nutrition
) -> FoodCapabilities:
    """What is configured on this server (photo recognition, nutrition data sources)."""
    return food_service.capabilities(settings, nutrition)


@router.post("/scan", response_model=ScanResponse, dependencies=[Depends(require_csrf_header)])
def scan(
    body: ScanRequest,
    user: CurrentUser,
    db: DbSession,
    storage: Storage,
    settings: AppSettings,
    make_provider: VisionFactory,
) -> ScanResponse:
    """Ask the vision model which foods it can see in one of the user's own photos."""
    return food_service.scan(db, storage, settings, user, body.media_id, make_provider)


@router.post(
    "/calculate", response_model=CalculationOut, dependencies=[Depends(require_csrf_header)]
)
def calculate(
    body: CalculateRequest, user: CurrentUser, db: DbSession, settings: AppSettings
) -> CalculationOut:
    """Deterministic preview of the confirmed items. Nothing is saved."""
    return food_service.calculate(db, settings, user, body, meal_service.load_audit)
