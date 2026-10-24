from typing import Literal

from pydantic import BaseModel


class ModelStatus(BaseModel):
    name: str | None
    configured: bool
    # None when it could not be determined (Ollama disabled or unreachable).
    installed: bool | None


class OllamaStatus(BaseModel):
    enabled: bool
    base_url: str
    reachable: bool | None
    text_model: ModelStatus
    vision_model: ModelStatus
    error: str | None = None


class AIStatus(BaseModel):
    ollama: OllamaStatus
    external_providers_allowed: bool
    fallback_policy: Literal["none"] = "none"


class HealthResponse(BaseModel):
    status: Literal["ok", "unavailable"]
    checks: dict[str, str] = {}
