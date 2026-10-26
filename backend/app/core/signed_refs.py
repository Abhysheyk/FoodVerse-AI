"""Tamper-proof references the client carries between steps.

The server never trusts model output or nutrient values echoed back by the browser. Instead, when
it produces a scan result or a nutrition candidate it signs the payload (HMAC-SHA256, bound to the
user and an expiry). The client sends the opaque token back, and the server verifies it and uses
the *embedded* data. This is how "the model identifies, the user confirms, trusted data supplies
the numbers" stays true even though the browser relays everything.

Tokens are signed, not encrypted: do not put secrets in them.
"""

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any

from app.core.config import Settings
from app.core.errors import AppError

_DOMAIN = b"foodverse.signed-ref.v1:"


class InvalidRefError(AppError):
    status_code = 422

    def __init__(self, message: str = "This reference is invalid or has expired.") -> None:
        super().__init__(message, code="invalid_reference")


def _key(settings: Settings, kind: str) -> bytes:
    return hashlib.sha256(
        _DOMAIN + kind.encode() + b":" + settings.jwt_secret_key.encode()
    ).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign_ref(settings: Settings, kind: str, user_id: uuid.UUID, payload: dict[str, Any]) -> str:
    body = {
        "k": kind,
        "u": str(user_id),
        "exp": int(time.time()) + settings.signed_ref_ttl_minutes * 60,
        "d": payload,
    }
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    sig = hmac.new(_key(settings, kind), raw, hashlib.sha256).digest()
    return f"{_b64(raw)}.{_b64(sig)}"


def verify_ref(settings: Settings, kind: str, user_id: uuid.UUID, token: str) -> dict[str, Any]:
    try:
        raw_b64, sig_b64 = token.split(".", 1)
        raw, sig = _unb64(raw_b64), _unb64(sig_b64)
        expected = hmac.new(_key(settings, kind), raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            raise InvalidRefError()
        body = json.loads(raw)
    except InvalidRefError:
        raise
    except (ValueError, TypeError):
        raise InvalidRefError() from None
    if (
        not isinstance(body, dict)
        or body.get("k") != kind
        or body.get("u") != str(user_id)  # a token is only valid for the user it was issued to
        or not isinstance(body.get("exp"), int)
        or body["exp"] < time.time()
        or not isinstance(body.get("d"), dict)
    ):
        raise InvalidRefError()
    return dict(body["d"])
