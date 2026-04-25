from __future__ import annotations

from typing import Any

from fastapi import status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable support-safe error code.")
    message: str = Field(description="Support-safe error message.")
    correlation_id: str = Field(description="Correlation identifier for support tracing.")
    service: str = Field(description="Service that produced the error.")


class ErrorEnvelope(BaseModel):
    error: ErrorDetail = Field(description="Support-safe error payload.")


SAFE_ERROR_MESSAGES: dict[str, str] = {
    "not_found": "The requested resource was not found.",
    "validation_failed": "The request could not be validated.",
    "internal_error": "The request could not be completed.",
    "caller_context_missing": "Required caller context is missing.",
    "authorization_failed": "The caller is not authorized for this archive action.",
    "document_not_found": "The requested archived document was not found.",
    "document_binary_missing": "The archived document binary could not be found.",
    "document_checksum_mismatch": "The archived document failed integrity verification.",
    "duplicate_archive_request": "The archive request conflicts with an existing document.",
    "metadata_validation_failed": "The archive metadata could not be validated.",
    "storage_read_failed": "The archived document could not be read.",
    "legal_hold_active": "A legal hold blocks this archive action.",
    "legal_hold_not_found": "The requested legal hold was not found.",
    "purge_not_eligible": "The archived document is not eligible for purge.",
    "supersession_conflict": "The requested lifecycle relationship conflicts with document history.",
    "unsupported_lifecycle_transition": "The requested lifecycle transition is not supported.",
}


def error_response(
    *,
    code: str,
    correlation_id: str,
    service: str,
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    message: str | None = None,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message or SAFE_ERROR_MESSAGES.get(code, SAFE_ERROR_MESSAGES["internal_error"]),
            correlation_id=correlation_id,
            service=service,
        )
    )
    return JSONResponse(status_code=http_status, content=envelope.model_dump(by_alias=True))


def error_response_schema() -> dict[str, Any]:
    return ErrorEnvelope.model_json_schema()
