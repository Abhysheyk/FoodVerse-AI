"""Text-generation provider interface.

Mirrors the vision layer: one configured provider, no silent fallback, typed errors with
user-safe messages, and a single `complete()` call that every feature shares.
"""

from typing import Any, Literal, Protocol

from pydantic import BaseModel

from app.core.errors import AppError


class TextError(AppError):
    """Base for every failure of a text-generation call."""


class TextUnavailableError(TextError):
    status_code = 503
    code = "text_unavailable"


class TextModelMissingError(TextError):
    status_code = 503
    code = "text_model_missing"


class TextTimeoutError(TextError):
    status_code = 504
    code = "text_timeout"


class TextBadOutputError(TextError):
    status_code = 502
    code = "text_bad_output"


class TextRateLimitedError(TextError):
    status_code = 429
    code = "text_rate_limited"


class TextProviderInfo(BaseModel):
    name: str
    model: str
    external: bool  # True when the prompt leaves this machine/network


class ChatTurn(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class TextProvider(Protocol):
    info: TextProviderInfo

    def complete(self, messages: list[ChatTurn], schema: dict[str, Any] | None = None) -> str:
        """Return the model's raw text. The caller owns validation; nothing is repaired here."""
        ...