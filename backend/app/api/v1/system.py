from functools import lru_cache
from typing import Annotated

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.ai.ollama import OllamaClient
from app.api.deps import CurrentUser, DbSession, get_ollama_client
from app.core.config import BACKEND_DIR
from app.schemas.meta import PreferenceOptions
from app.schemas.system import AIStatus, HealthResponse

router = APIRouter(tags=["system"])


@lru_cache
def _migration_head() -> str | None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness: the process is up. Does not touch the database."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
def ready(db: DbSession) -> HealthResponse | JSONResponse:
    """Readiness: the database is reachable and migrations are at the latest revision."""
    checks: dict[str, str] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except SQLAlchemyError:
        checks["database"] = "unreachable"
        return JSONResponse(
            HealthResponse(status="unavailable", checks=checks).model_dump(), status_code=503
        )
    try:
        current = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except SQLAlchemyError:
        db.rollback()
        current = None
    checks["migrations"] = "ok" if current == _migration_head() else "not_up_to_date"
    if checks["migrations"] != "ok":
        return JSONResponse(
            HealthResponse(status="unavailable", checks=checks).model_dump(), status_code=503
        )
    return HealthResponse(status="ok", checks=checks)


@router.get("/meta/preference-options", response_model=PreferenceOptions)
def preference_options() -> PreferenceOptions:
    return PreferenceOptions.current()


@router.get("/ai/status", response_model=AIStatus)
def ai_status(
    _user: CurrentUser, client: Annotated[OllamaClient, Depends(get_ollama_client)]
) -> AIStatus:
    """Read-only: what AI is configured and reachable. Never downloads or runs a model."""
    return client.status()
