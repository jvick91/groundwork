"""
Request-logging middleware (SPEC-006 §4 BR-08, TASK-007 AC).

Emits one structlog event per HTTP request with `method`, `path`,
`status_code`, and `duration_ms`. The shared phi_filter is in the
structlog processor chain, so any field name in PHI_EXCLUDED_FIELDS is
stripped before emission regardless of what is bound to the logger.

Implemented as pure ASGI middleware rather than `BaseHTTPMiddleware`
to avoid the streaming-response and exception-propagation pitfalls of
the latter. We always emit the log line, even when the downstream app
raises — the exception is re-raised after logging so FastAPI's exception
handlers run as usual.
"""

import time
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logger import get_logger

logger = get_logger("app.request")


class RequestLoggerMiddleware:
    """ASGI middleware that emits one log event per HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        method: str = scope.get("method", "")
        path: str = scope.get("path", "")

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            _emit(method=method, path=path, status_code=500, duration_ms=duration_ms)
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        _emit(method=method, path=path, status_code=status_code, duration_ms=duration_ms)


def _emit(*, method: str, path: str, status_code: int, duration_ms: float) -> None:
    """Emit one structured log event for the request.

    Kept as a free function so tests can assert on the exact field set
    (method, path, status_code, duration_ms) without reaching into the
    middleware class.
    """
    payload: dict[str, Any] = {
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": duration_ms,
    }
    logger.info("request", **payload)
