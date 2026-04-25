from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.archive.authorization import AuthorizationFailedError
from app.archive.exceptions import (
    DocumentChecksumMismatchError,
    DocumentNotFoundError,
    DuplicateArchiveRequestConflict,
    MetadataValidationError,
    StorageReadFailedError,
)
from app.contracts.errors import error_response
from app.security.caller_context import CallerContextMissingError


def register_archive_exception_handlers(
    app: FastAPI,
    *,
    service_name: str,
    correlation_id: Callable[[Request], str],
) -> None:
    @app.exception_handler(CallerContextMissingError)
    async def caller_context_missing_exception_handler(
        request: Request,
        _exc: CallerContextMissingError,
    ) -> JSONResponse:
        return error_response(
            code="caller_context_missing",
            http_status=status.HTTP_401_UNAUTHORIZED,
            correlation_id=correlation_id(request),
            service=service_name,
        )

    @app.exception_handler(AuthorizationFailedError)
    async def authorization_failed_exception_handler(
        request: Request,
        _exc: AuthorizationFailedError,
    ) -> JSONResponse:
        return error_response(
            code="authorization_failed",
            http_status=status.HTTP_403_FORBIDDEN,
            correlation_id=correlation_id(request),
            service=service_name,
        )

    @app.exception_handler(DocumentNotFoundError)
    async def document_not_found_exception_handler(
        request: Request,
        _exc: DocumentNotFoundError,
    ) -> JSONResponse:
        return error_response(
            code="document_not_found",
            http_status=status.HTTP_404_NOT_FOUND,
            correlation_id=correlation_id(request),
            service=service_name,
        )

    @app.exception_handler(StorageReadFailedError)
    async def storage_read_failed_exception_handler(
        request: Request,
        _exc: StorageReadFailedError,
    ) -> JSONResponse:
        return error_response(
            code="document_binary_missing",
            http_status=status.HTTP_404_NOT_FOUND,
            correlation_id=correlation_id(request),
            service=service_name,
        )

    @app.exception_handler(DocumentChecksumMismatchError)
    async def checksum_mismatch_exception_handler(
        request: Request,
        _exc: DocumentChecksumMismatchError,
    ) -> JSONResponse:
        return error_response(
            code="document_checksum_mismatch",
            http_status=status.HTTP_409_CONFLICT,
            correlation_id=correlation_id(request),
            service=service_name,
        )

    @app.exception_handler(DuplicateArchiveRequestConflict)
    async def duplicate_archive_request_exception_handler(
        request: Request,
        _exc: DuplicateArchiveRequestConflict,
    ) -> JSONResponse:
        return error_response(
            code="duplicate_archive_request",
            http_status=status.HTTP_409_CONFLICT,
            correlation_id=correlation_id(request),
            service=service_name,
        )

    @app.exception_handler(MetadataValidationError)
    async def metadata_validation_exception_handler(
        request: Request,
        _exc: MetadataValidationError,
    ) -> JSONResponse:
        return error_response(
            code="metadata_validation_failed",
            http_status=status.HTTP_400_BAD_REQUEST,
            correlation_id=correlation_id(request),
            service=service_name,
        )
