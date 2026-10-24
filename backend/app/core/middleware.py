"""Pure-ASGI middleware: request id, access log, and baseline security headers.

Written as raw ASGI (not BaseHTTPMiddleware) so the request id is available to exception
handlers and so response headers are applied to every response, including errors.
Query strings and bodies are never logged.
"""

import json
import logging
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import PayloadTooLargeError
from app.core.logging import request_id_ctx

logger = logging.getLogger("app.access")

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                for name, value in _SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            logger.info(
                "%s %s -> %s (%.1f ms)",
                scope["method"],
                scope["path"],
                status_code,
                (time.perf_counter() - started) * 1000,
            )
            request_id_ctx.reset(token)


class _BodyTooLarge(Exception):
    """Raised from `receive` to abort body parsing once the limit is exceeded."""


class BodySizeLimitMiddleware:
    """Reject oversized request bodies before they are buffered.

    Checks Content-Length up front (no body is read at all) and also counts bytes as they
    stream in, so a client that lies about, or omits, Content-Length cannot push an unbounded
    body through. The 413 is written here rather than raised as an app error because FastAPI
    rewrites exceptions raised during body parsing into a generic 400.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int, path_prefix: str) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.path_prefix = path_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self.path_prefix):
            await self.app(scope, receive, send)
            return

        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(scope, send)
            return

        received = 0
        tripped = False

        async def limited_receive() -> Message:
            nonlocal received, tripped
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    tripped = True
                    raise _BodyTooLarge
            return message

        async def guarded_send(message: Message) -> None:
            if tripped:  # discard whatever the app produced; we answer 413 ourselves
                return
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            pass
        if tripped:
            await self._reject(scope, send)

    async def _reject(self, scope: Scope, send: Send) -> None:
        error = PayloadTooLargeError("Request body is too large.")
        body = json.dumps(
            {
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": None,
                    "request_id": scope.get("state", {}).get("request_id"),
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": error.status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
