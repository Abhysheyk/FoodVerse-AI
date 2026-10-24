"""Read-only status check for an optional local Ollama server.

Phase 1 only reports what is configured and what is installed. It never pulls or downloads
models and never runs inference.
"""

import httpx

from app.core.config import Settings
from app.schemas.system import AIStatus, ModelStatus, OllamaStatus

_STATUS_TIMEOUT_SECONDS = 3.0


def _is_installed(name: str, installed: set[str]) -> bool:
    return name in installed or f"{name}:latest" in installed


class OllamaClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport

    def status(self) -> AIStatus:
        s = self._settings
        text_name = s.ollama_text_model or None
        vision_name = s.ollama_vision_model or None
        installed: set[str] | None = None
        reachable: bool | None = None
        error: str | None = None

        if s.ollama_enabled:
            try:
                with httpx.Client(
                    transport=self._transport, timeout=_STATUS_TIMEOUT_SECONDS
                ) as client:
                    response = client.get(f"{s.ollama_base_url}/api/tags")
                    response.raise_for_status()
                    models = response.json().get("models", [])
                    installed = {str(m.get("name")) for m in models if isinstance(m, dict)}
                    reachable = True
            except (httpx.HTTPError, ValueError) as exc:
                reachable = False
                error = f"Could not read model list from Ollama ({type(exc).__name__})."

        def model_status(name: str | None) -> ModelStatus:
            return ModelStatus(
                name=name,
                configured=name is not None,
                installed=(
                    _is_installed(name, installed) if name and installed is not None else None
                ),
            )

        return AIStatus(
            ollama=OllamaStatus(
                enabled=s.ollama_enabled,
                base_url=s.ollama_base_url,
                reachable=reachable,
                text_model=model_status(text_name),
                vision_model=model_status(vision_name),
                error=error,
            ),
            external_providers_allowed=s.allow_external_ai_providers,
        )
