from fastapi import status
from fastapi.exceptions import RequestValidationError
import pytest
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.contracts.errors import error_response, error_response_schema
from app.main import (
    HTTP_422_UNPROCESSABLE_CONTENT,
    http_exception_handler,
    request_validation_exception_handler,
    unhandled_exception_handler,
)


def test_error_response_uses_support_safe_envelope() -> None:
    response = error_response(
        code="storage_read_failed",
        correlation_id="corr-123",
        service="lotus-archive",
        http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert b"storage_read_failed" in response.body
    assert b"The request could not be completed." in response.body
    assert b"bucket" not in response.body
    assert b"object" not in response.body


def test_error_response_schema_documents_envelope_shape() -> None:
    schema = error_response_schema()

    assert schema["properties"]["error"]["description"] == "Support-safe error payload."
    error_detail = schema["$defs"]["ErrorDetail"]["properties"]
    assert error_detail["code"]["description"] == "Stable support-safe error code."
    assert error_detail["correlation_id"]["description"]


def _request_with_correlation(correlation_id: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/documents/example",
            "headers": [(b"x-correlation-id", correlation_id.encode())],
        }
    )


@pytest.mark.asyncio
async def test_http_exception_handler_maps_non_not_found_to_safe_error() -> None:
    response = await http_exception_handler(
        _request_with_correlation("corr-http"),
        StarletteHTTPException(status_code=status.HTTP_403_FORBIDDEN),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert b"internal_error" in response.body
    assert b"corr-http" in response.body


@pytest.mark.asyncio
async def test_validation_exception_handler_uses_safe_error_code() -> None:
    response = await request_validation_exception_handler(
        _request_with_correlation("corr-validation"),
        RequestValidationError([]),
    )

    assert response.status_code == HTTP_422_UNPROCESSABLE_CONTENT
    assert b"validation_failed" in response.body
    assert b"corr-validation" in response.body


@pytest.mark.asyncio
async def test_unhandled_exception_handler_does_not_expose_exception_detail() -> None:
    response = await unhandled_exception_handler(
        _request_with_correlation("corr-internal"),
        RuntimeError("secret object bucket path"),
    )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert b"internal_error" in response.body
    assert b"secret" not in response.body
    assert b"bucket" not in response.body
