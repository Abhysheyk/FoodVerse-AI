"""Vision via a local Ollama server (the default; no data leaves the machine)."""

from typing import Any

import httpx

from app.ai.vision import (
    VISION_JSON_SCHEMA,
    VISION_PROMPT,
    VisionBadOutputError,
    VisionModelMissingError,
    VisionProviderInfo,
    VisionRateLimitedError,
    VisionResult,
    VisionTimeoutError,
    VisionUnavailableError,
    parse_vision_output,
    prepare_image_for_model,
    to_base64,
)


class OllamaVisionProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = httpx.Timeout(timeout_seconds, connect=5.0)
        self._transport = transport
        self.info = VisionProviderInfo(name="ollama", model=model, external=False)

    def identify(self, image: bytes) -> VisionResult:
        return parse_vision_output(self.complete_json(image, VISION_PROMPT, VISION_JSON_SCHEMA))

    def complete_json(self, image: bytes, prompt: str, schema: dict[str, Any]) -> str:
        payload = {
            "model": self._model,
            "stream": False,
            "format": schema,
            "options": {"temperature": 0},
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [to_base64(prepare_image_for_model(image))],
                }
            ],
        }
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(f"{self._base_url}/api/chat", json=payload)
        except httpx.ConnectTimeout:
            raise VisionUnavailableError(
                "Could not connect to the local model server. Is Ollama running?"
            ) from None
        except httpx.TimeoutException:
            raise VisionTimeoutError(
                "The vision model took too long to answer. CPU-only machines can be slow; "
                "try a smaller model or increase OLLAMA_TIMEOUT_SECONDS."
            ) from None
        except httpx.ConnectError:
            raise VisionUnavailableError(
                "Could not reach the local model server. Is Ollama running?"
            ) from None
        except httpx.HTTPError:
            raise VisionUnavailableError("The local model server request failed.") from None

        if response.status_code == 404:
            raise VisionModelMissingError(
                f"The vision model '{self._model}' is not installed. "
                f"Install it yourself with: ollama pull {self._model}"
            )
        if response.status_code == 429:
            raise VisionRateLimitedError("The model server is busy. Please try again shortly.")
        if response.status_code >= 400:
            raise VisionUnavailableError(
                f"The local model server returned an error (HTTP {response.status_code})."
            )
        try:
            envelope = response.json()
            content = envelope["message"]["content"]
        except (ValueError, KeyError, TypeError):
            raise VisionBadOutputError(
                "The model server returned a response in an unexpected format."
            ) from None
        if not isinstance(content, str):
            raise VisionBadOutputError(
                "The model server returned a response in an unexpected format."
            )
        return content
