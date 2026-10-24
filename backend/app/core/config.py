"""Application configuration, loaded from environment variables (and an optional .env file).

Nothing here has a secret default: the app refuses to start without DATABASE_URL and
JWT_SECRET_KEY. AI settings are opt-in and never imply a paid provider.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---
    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    enable_api_docs: bool = True

    # --- Database ---
    database_url: str

    # --- Auth / sessions (see docs/adr/0001-auth-session-strategy.md) ---
    jwt_secret_key: str = Field(min_length=32)
    access_token_expire_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_expire_days: int = Field(default=14, ge=1, le=90)
    cookie_secure: bool = True
    cookie_samesite: Literal["strict", "lax", "none"] = "strict"

    # --- CORS (comma-separated list of exact origins) ---
    cors_allowed_origins: str = "http://localhost:5173"

    # --- AI (all optional; nothing is downloaded or called unless enabled) ---
    ollama_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_text_model: str = ""
    ollama_vision_model: str = ""
    ollama_timeout_seconds: float = Field(default=120.0, gt=0, le=1800)
    # Policy flag only. Phase 1 contains no external provider adapters; this exists so a
    # future adapter must be explicitly enabled and can never be used as a silent fallback.
    allow_external_ai_providers: bool = False

    # --- Media (see docs/adr/0002-media-storage.md) ---
    # Uploaded files are stored here. The default is in the user's home directory, i.e.
    # outside this repository and any web root. Point it at a dedicated data volume in production.
    media_root: Path = Path.home() / ".foodverse" / "media"
    max_upload_bytes: int = Field(default=8 * 1024 * 1024, ge=1024, le=64 * 1024 * 1024)
    max_image_pixels: int = Field(default=40_000_000, ge=10_000, le=200_000_000)
    user_media_quota_bytes: int = Field(default=500 * 1024 * 1024, ge=1024)

    @field_validator("media_root")
    @classmethod
    def _absolute_media_root(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+psycopg://", 1)
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL (postgresql+psycopg://...)")
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def _validate_cors(cls, value: str) -> str:
        for origin in (o.strip() for o in value.split(",") if o.strip()):
            if origin == "*":
                raise ValueError("CORS_ALLOWED_ORIGINS must not contain '*' (credentials are used)")
            if not origin.startswith(("http://", "https://")):
                raise ValueError(f"Invalid CORS origin: {origin!r}")
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def _validate_ollama_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("OLLAMA_BASE_URL must start with http:// or https://")
        return value.rstrip("/")

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
        if self.app_env == "production":
            if self.jwt_secret_key.lower().startswith("replace"):
                raise ValueError("JWT_SECRET_KEY is still the placeholder value")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
            if not self.cors_origins:
                raise ValueError("CORS_ALLOWED_ORIGINS must be set in production")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
