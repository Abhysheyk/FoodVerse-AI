"""Vision provider interface and strict validation of what a model returns.

A vision model's only job here is to *name candidate foods it can see*. It is never asked for
weights, calories or nutrition, and any such fields it volunteers are ignored. It is also never
asked for a confidence number: small local models do not produce calibrated probabilities, and a
made-up 0.87 would be misleading. Uncertainty is therefore reported only as what the model says
about each item ("ambiguous" plus alternative names), labelled as the model's own statement.
"""

import base64
import io
import json
import re
import unicodedata
from typing import Any, Protocol

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.errors import AppError

MAX_ITEMS = 15
MAX_NAME = 80

VISION_PROMPT = (
    "You are a food identification assistant. Look at the photo and list each distinct food or "
    "drink you can actually see. For every item give: a short generic name (for example "
    "'white rice' or 'grilled chicken'), one sentence describing what it looks like, whether you "
    "are unsure what it is (ambiguous), and up to 3 alternative names if you are unsure. "
    "Do NOT estimate weights, portion sizes, calories or any nutrition. Do NOT guess items that "
    "are not visible. If no food is visible, return an empty list. "
    'Reply with JSON only, in this shape: {"items": [{"name": str, "description": str, '
    '"ambiguous": bool, "alternatives": [str]}], "notes": str}.'
)

# Flat JSON schema handed to servers that support constrained decoding (Ollama "format").
VISION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "ambiguous": {"type": "boolean"},
                    "alternatives": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "description", "ambiguous", "alternatives"],
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["items"],
}


class VisionError(AppError):
    """Base for every failure of the vision step. Never carries partial or guessed results."""


class VisionUnavailableError(VisionError):
    status_code = 503
    code = "vision_unavailable"


class VisionModelMissingError(VisionError):
    status_code = 503
    code = "vision_model_missing"


class VisionTimeoutError(VisionError):
    status_code = 504
    code = "vision_timeout"


class VisionBadOutputError(VisionError):
    status_code = 502
    code = "vision_bad_output"


class VisionRateLimitedError(VisionError):
    status_code = 429
    code = "vision_rate_limited"


class DetectedFood(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=MAX_NAME)
    description: str = Field(default="", max_length=300)
    ambiguous: bool = False
    alternatives: list[str] = Field(default_factory=list, max_length=3)


class VisionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[DetectedFood] = Field(max_length=MAX_ITEMS)
    notes: str | None = Field(default=None, max_length=500)


class VisionProviderInfo(BaseModel):
    name: str
    model: str
    external: bool  # True when the photo leaves this machine/network


class VisionProvider(Protocol):
    info: VisionProviderInfo

    def identify(self, image: bytes) -> VisionResult:
        """Return candidate foods for a validated image, or raise a VisionError."""
        ...


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFC", _CONTROL.sub(" ", text))
    return " ".join(text.split()).strip(" -•*·\t")


def parse_vision_output(text: object) -> VisionResult:
    """Validate raw model text against the schema. Anything off is rejected, never repaired."""
    if not isinstance(text, str) or not text.strip():
        raise VisionBadOutputError("The vision model returned an empty response.")
    try:
        data = json.loads(_FENCE.sub("", text.strip()))
    except json.JSONDecodeError:
        raise VisionBadOutputError(
            "The vision model did not return valid JSON, so its answer was discarded."
        ) from None
    if not isinstance(data, dict):
        raise VisionBadOutputError("The vision model returned an unexpected structure.")
    try:
        result = VisionResult.model_validate(data)
    except ValidationError:
        raise VisionBadOutputError(
            "The vision model's answer did not match the expected format, so it was discarded."
        ) from None

    items: list[DetectedFood] = []
    seen: set[str] = set()
    for item in result.items:
        name = _clean(item.name)
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        alternatives = []
        for alt in item.alternatives:
            cleaned = _clean(alt)
            if cleaned and cleaned.casefold() != key and cleaned not in alternatives:
                alternatives.append(cleaned[:MAX_NAME])
        items.append(
            DetectedFood(
                name=name,
                description=_clean(item.description),
                ambiguous=item.ambiguous,
                alternatives=alternatives,
            )
        )
    notes = _clean(result.notes) if result.notes else None
    return VisionResult(items=items, notes=notes or None)


def prepare_image_for_model(data: bytes, max_side: int = 1024) -> bytes:
    """Downscale for speed (CPU-only machines) and flatten to JPEG. Input is already validated."""
    with Image.open(io.BytesIO(data)) as opened:
        opened.load()
        opened.thumbnail((max_side, max_side))
        flat: Image.Image
        if opened.mode in ("RGBA", "LA", "P"):
            rgba = opened.convert("RGBA")
            flat = Image.new("RGB", rgba.size, (255, 255, 255))
            flat.paste(rgba, mask=rgba.split()[3])
        elif opened.mode != "RGB":
            flat = opened.convert("RGB")
        else:
            flat = opened
        out = io.BytesIO()
        flat.save(out, "JPEG", quality=85)
    return out.getvalue()


def to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
