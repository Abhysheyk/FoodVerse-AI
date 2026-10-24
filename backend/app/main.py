import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware

logger = logging.getLogger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    docs = settings.enable_api_docs
    app = FastAPI(
        title="FoodVerse AI API",
        version="0.1.0",
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
    )
    register_exception_handlers(app)
    app.include_router(api_router)

    # Added last = outermost. CORS answers preflights before anything else; request context
    # wraps everything so every response (including CORS and error responses) gets headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
    )
    app.add_middleware(RequestContextMiddleware)

    logger.info("app_started env=%s ollama_enabled=%s", settings.app_env, settings.ollama_enabled)
    return app


app = create_app()
