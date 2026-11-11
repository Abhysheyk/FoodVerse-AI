"""Chooses the configured AI provider. There is exactly one; no silent fallbacks."""

import httpx

from app.ai.ollama_vision import OllamaVisionProvider
from app.ai.openai_text import OpenAICompatibleTextProvider
from app.ai.openai_vision import OpenAICompatibleVisionProvider
from app.ai.text import TextProvider, TextUnavailableError
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


def build_text_provider(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> TextProvider:
    if settings.text_provider == "none":
        raise TextUnavailableError(
            "Meal plan generation is not configured on this server. You can still create a "
            "blank plan and edit it manually. (Server setup: TEXT_PROVIDER=openai_compatible "
            "with TEXT_API_BASE_URL, TEXT_API_KEY, TEXT_API_MODEL, and "
            "ALLOW_EXTERNAL_AI_PROVIDERS=true.)"
        )
    key = settings.text_api_key.get_secret_value() if settings.text_api_key else None
    return OpenAICompatibleTextProvider(
        settings.text_api_base_url,
        settings.text_api_model,
        key,
        settings.text_timeout_seconds,
        transport,
    )