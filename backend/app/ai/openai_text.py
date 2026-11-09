"""Text generation via an OpenAI-compatible /chat/completions server.

Opt-in only. The API key is placed in the Authorization header and is never logged or returned.
"""

from typing import Any

import httpx

from app.ai.openai_vision import is_local_url
from app.ai.text import (
    ChatTurn,
    TextBadOutputError,
    TextProviderInfo,
    TextRateLimitedError,
    TextTimeoutError,
    TextUnavailableError,
)


class OpenAICompatibleTextProvider:
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
        self.info = TextProviderInfo(
            name="openai_compatible", model=model, external=not is_local_url(base_url)
        )

    def complete(self, messages: list[ChatTurn], schema: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self._model,
            "temperature": 0,
            "messages": [m.model_dump() for m in messages],
        }
        if schema is not None:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
        except httpx.ConnectTimeout:
            raise TextUnavailableError("Could not connect to the text provider.") from None
        except httpx.TimeoutException:
            raise TextTimeoutError("The text provider took too long to answer.") from None
        except httpx.HTTPError:
            raise TextUnavailableError("Could not reach the text provider.") from None

        if response.status_code == 429:
            raise TextRateLimitedError(
                "The text provider is rate limiting requests. Please try again shortly."
            )
        if response.status_code in (401, 403):
            raise TextUnavailableError("The text provider rejected the configured credentials.")
        if response.status_code >= 400:
            raise TextUnavailableError(
                f"The text provider returned an error (HTTP {response.status_code})."
            )
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise TextBadOutputError(
                "The text provider returned a response in an unexpected format."
            ) from None
        if not isinstance(content, str):
            raise TextBadOutputError(
                "The text provider returned a response in an unexpected format."
            )
        return content