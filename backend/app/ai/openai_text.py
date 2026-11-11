"""Text generation via any OpenAI-compatible /chat/completions server.

Groq, OpenRouter, Together and Gemini's OpenAI endpoint all expose this shape. Free tiers
are enough for this app. The API key is only ever placed in the Authorization header and is
never logged or included in an error message.
"""

import json
from typing import Any
from urllib.parse import urlparse

import httpx

from app.ai.text import (
    ChatTurn,
    TextBadOutputError,
    TextProviderInfo,
    TextRateLimitedError,
    TextTimeoutError,
    TextUnavailableError,
)

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def _is_local(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in _LOCAL_HOSTS or host.startswith("127.")


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
            name="openai_compatible", model=model, external=not _is_local(base_url)
        )

    def _post(self, payload: dict[str, Any]) -> str:
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
                "The text provider is rate limiting requests. Try again shortly."
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
        return content.strip()

    def complete_json(self, prompt: str, schema: dict[str, Any]) -> str:
        payload = {
            "model": self._model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "Reply with a single JSON object and nothing else."},
                {"role": "user", "content": prompt},
            ],
        }
        content = self._post(payload)
        # Some providers wrap JSON in ```json fences even with response_format=json_object.
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].lower().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()
        try:
            json.loads(content)
        except json.JSONDecodeError:
            raise TextBadOutputError("The text provider did not return valid JSON.") from None
        return content

    def chat(self, turns: list[ChatTurn]) -> str:
        payload = {
            "model": self._model,
            "temperature": 0.6,
            "messages": [{"role": t.role, "content": t.content} for t in turns],
        }
        return self._post(payload)