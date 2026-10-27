"""Vision via an OpenAI-compatible /chat/completions server.

Opt-in only (see Settings): the same adapter can point at a local llama.cpp/vLLM/LM Studio
server or at a hosted API. It is never used as a fallback for Ollama. The API key is only ever
placed in the Authorization header and is never logged or returned in an error.
"""

from typing import Any
from urllib.parse import urlparse

import httpx

from app.ai.vision import (
    VISION_JSON_SCHEMA,
    VISION_PROMPT,
    VisionBadOutputError,
    VisionProviderInfo,
    VisionRateLimitedError,
    VisionResult,
    VisionTimeoutError,
    VisionUnavailableError,
    parse_vision_output,
    prepare_image_for_model,
    to_base64,
)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def is_local_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in _LOCAL_HOSTS or host.startswith("127.")


class OpenAICompatibleVisionProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = httpx.Timeout(timeout_seconds, connect=5.0)
        self._transport = transport
        self.info = VisionProviderInfo(
            name="openai_compatible", model=model, external=not is_local_url(base_url)
        )

    def identify(self, image: bytes) -> VisionResult:
        return parse_vision_output(self.complete_json(image, VISION_PROMPT, VISION_JSON_SCHEMA))

    def complete_json(self, image: bytes, prompt: str, schema: dict[str, Any]) -> str:
        data_url = "data:image/jpeg;base64," + to_base64(prepare_image_for_model(image))
        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        }
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
        except httpx.ConnectTimeout:
            raise VisionUnavailableError("Could not connect to the vision provider.") from None
        except httpx.TimeoutException:
            raise VisionTimeoutError("The vision provider took too long to answer.") from None
        except httpx.HTTPError:
            raise VisionUnavailableError("Could not reach the vision provider.") from None

        if response.status_code == 429:
            raise VisionRateLimitedError(
                "The vision provider is rate limiting requests. Please try again shortly."
            )
        if response.status_code in (401, 403):
            raise VisionUnavailableError("The vision provider rejected the configured credentials.")
        if response.status_code >= 400:
            raise VisionUnavailableError(
                f"The vision provider returned an error (HTTP {response.status_code})."
            )
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise VisionBadOutputError(
                "The vision provider returned a response in an unexpected format."
            ) from None
        if not isinstance(content, str):
            raise VisionBadOutputError(
                "The vision provider returned a response in an unexpected format."
            )
        return content
