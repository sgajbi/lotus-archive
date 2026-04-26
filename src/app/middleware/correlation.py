from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

LOGGER = logging.getLogger("lotus_archive.requests")
REQUEST_LOG_HANDLER_MARKER = "_lotus_archive_request_log_handler"

_W3C_TRACE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def configure_request_logging() -> None:
    LOGGER.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    if not any(getattr(handler, REQUEST_LOG_HANDLER_MARKER, False) for handler in LOGGER.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        setattr(handler, REQUEST_LOG_HANDLER_MARKER, True)
        LOGGER.addHandler(handler)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, service_name: str) -> None:
        super().__init__(app)
        self._service_name = service_name

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        trace_id = _resolve_trace_id(request) or uuid.uuid4().hex
        request.state.correlation_id = correlation_id
        request.state.trace_id = trace_id
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Correlation-Id"] = correlation_id
        response.headers["X-Trace-Id"] = trace_id
        traceparent = _traceparent_header(trace_id)
        if traceparent:
            response.headers["traceparent"] = traceparent
        response.headers["X-Service-Name"] = self._service_name
        response.headers["X-Request-Duration-Ms"] = f"{duration_ms:.3f}"
        LOGGER.info(
            json.dumps(
                {
                    "event": "request_completed",
                    "service": self._service_name,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "correlation_id": correlation_id,
                    "trace_id": trace_id,
                    "duration_ms": round(duration_ms, 3),
                },
                sort_keys=True,
            )
        )
        return response


def _resolve_trace_id(request: Request) -> str | None:
    traceparent = request.headers.get("traceparent")
    if traceparent:
        parts = traceparent.split("-")
        if len(parts) >= 4 and _is_w3c_trace_id(parts[1]):
            return parts[1]
    return request.headers.get("X-Trace-Id") or request.headers.get("X-Trace-ID")


def _is_w3c_trace_id(trace_id: str) -> bool:
    return bool(_W3C_TRACE_ID_PATTERN.fullmatch(trace_id))


def _traceparent_header(trace_id: str) -> str | None:
    if not _is_w3c_trace_id(trace_id):
        return None
    return f"00-{trace_id}-0000000000000001-01"
