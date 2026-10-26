"""Chooses the configured vision provider. There is exactly one; no silent fallbacks."""

import httpx

from app.ai.ollama_vision import OllamaVisionProvider
from app.ai.openai_vision import OpenAICompatibleVisionProvider
from app.ai.vision import VisionProvider, VisionUnavailableError
from app.core.config import Settings


def build_vision_provider(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> VisionProvider:
    if settings.vision_provider == "openai_compatible":
        key = settings.vision_api_key.get_secret_value() if settings.vision_api_key else None
        return OpenAICompatibleVisionProvider(
            settings.vision_api_base_url,
            settings.vision_api_model,
            key,
            settings.vision_timeout_seconds,
            transport,
        )
    if not settings.ollama_enabled:
        raise VisionUnavailableError(
            "Photo recognition is not enabled on this server. You can still add foods "
            "manually. (Server setup: OLLAMA_ENABLED=true and OLLAMA_VISION_MODEL.)"
        )
    if not settings.ollama_vision_model:
        raise VisionUnavailableError(
            "No vision model is configured on this server (OLLAMA_VISION_MODEL). "
            "You can still add foods manually."
        )
    return OllamaVisionProvider(
        settings.ollama_base_url,
        settings.ollama_vision_model,
        settings.ollama_timeout_seconds,
        transport,
    )
