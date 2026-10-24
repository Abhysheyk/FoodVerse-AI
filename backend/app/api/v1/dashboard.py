from fastapi import APIRouter

from app.api.deps import AppSettings, CurrentUser, DbSession
from app.domain.modules import MODULES
from app.schemas.dashboard import DashboardSummary, ModuleRead
from app.services import dashboard_service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(user: CurrentUser, db: DbSession, settings: AppSettings) -> DashboardSummary:
    return dashboard_service.summary(db, settings, user)


@router.get("/modules", response_model=list[ModuleRead])
def list_modules(_user: CurrentUser) -> list[ModuleRead]:
    return [
        ModuleRead(key=m.key, title=m.title, description=m.description, available=m.available)
        for m in MODULES
    ]
