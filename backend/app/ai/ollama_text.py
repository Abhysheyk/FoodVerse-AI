"""Text generation via a local Ollama server (default; nothing leaves the machine)."""

from typing import Any

import httpx

from app.ai.text import (
    ChatTurn,
    TextBadOutputError,
    TextModelMissingError,
    TextProviderInfo,
    TextRateLimitedError,
    TextTimeoutError,
    TextUnavailableError,
)


class OllamaTextProvider:
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
        self.info = TextProviderInfo(name="ollama", model=model, external=False)

    def complete(self, messages: list[ChatTurn], schema: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "stream": False,
            "options": {"temperature": 0},
            "messages": [m.model_dump() for m in messages],
        }
        if schema is not None:
            payload["format"] = schema
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(f"{self._base_url}/api/chat", json=payload)
        except httpx.ConnectTimeout:
            raise TextUnavailableError(
                "Could not connect to the local model server. Is Ollama running?"
            ) from None
        except httpx.TimeoutException:
            raise TextTimeoutError(
                "The text model took too long to answer. CPU-only machines can be slow; try a "
                "smaller model or raise OLLAMA_TIMEOUT_SECONDS."
            ) from None
        except httpx.ConnectError:
            raise TextUnavailableError(
                "Could not reach the local model server. Is Ollama running?"
            ) from None
        except httpx.HTTPError:
            raise TextUnavailableError("The local model server request failed.") from None

        if response.status_code == 404:
            raise TextModelMissingError(
                f"The text model '{self._model}' is not installed. "
                f"Install it yourself with: ollama pull {self._model}"
            )
        if response.status_code == 429:
            raise TextRateLimitedError("The model server is busy. Please try again shortly.")
        if response.status_code >= 400:
            raise TextUnavailableError(
                f"The local model server returned an error (HTTP {response.status_code})."
            )
        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError):
            raise TextBadOutputError(
                "The model server returned a response in an unexpected format."
            ) from None
        if not isinstance(content, str):
            raise TextBadOutputError(
                "The model server returned a response in an unexpected format."
            )
        return content