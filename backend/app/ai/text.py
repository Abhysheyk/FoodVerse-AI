"""Text generation provider interface used by cooking (multi-turn) and meal planning
(single-shot JSON). Mirrors the VisionProvider contract: exactly one provider is configured,
never falls back, and the caller owns validation of what the model said.
"""

from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from app.core.errors import AppError


class TextError(AppError):
    """Base for every failure of a text-generation call. Never carries partial output."""


class TextUnavailableError(TextError):
    status_code = 503
    code = "text_unavailable"


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
    external: bool  # True when prompts leave this machine/network


@dataclass(frozen=True)
class ChatTurn:
    """One turn in a multi-turn chat (used by the cooking assistant)."""

    role: Literal["system", "user", "assistant"]
    content: str


class TextProvider(Protocol):
    info: TextProviderInfo

    def complete_json(self, prompt: str, schema: dict[str, Any]) -> str:
        """Single-shot: send a prompt, return the model's raw text (a JSON document)."""
        ...

    def chat(self, turns: list[ChatTurn]) -> str:
        """Multi-turn: send a conversation history, return the next assistant reply as text."""
        ...