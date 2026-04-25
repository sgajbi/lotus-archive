from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi import APIRouter, Depends, Request, Response, status

from app.archive.api_models import (
    AccessEventListResponse,
    ArchiveDocumentCreateRequest,
    ArchiveDocumentResponse,
)
from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import InMemoryAccessAuditRepository
from app.archive.repository import InMemoryArchiveDocumentRepository
from app.archive.service import ArchiveDocumentService
from app.archive.storage import FilesystemObjectStorage
from app.security.caller_context import CallerContext, caller_context_from_headers

ARCHIVE_API_TAG = "Archive Documents"

router = APIRouter(prefix="/documents", tags=[ARCHIVE_API_TAG])


def build_default_archive_service() -> ArchiveDocumentService:
    repository = InMemoryArchiveDocumentRepository()
    storage = FilesystemObjectStorage(Path(tempfile.gettempdir()) / "lotus-archive-objects")
    return ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=InMemoryAccessAuditRepository(),
    )


def archive_service(request: Request) -> ArchiveDocumentService:
    service = getattr(request.app.state, "archive_service", None)
    if service is None:
        service = build_default_archive_service()
        request.app.state.archive_service = service
    return service


def caller_context(request: Request) -> CallerContext:
    return caller_context_from_headers(
        request.headers,
        correlation_id=str(getattr(request.state, "correlation_id", "")),
    )


def trace_id(request: Request) -> str:
    return str(getattr(request.state, "trace_id", getattr(request.state, "correlation_id", "")))


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ArchiveDocumentResponse,
    summary="Archive a generated document",
    description=(
        "Stores a generated Lotus reporting document with source-backed metadata, checksum "
        "validation, idempotent archive request handling, and access-audit evidence. Use this "
        "after a render succeeds and the caller has archive authority."
    ),
    responses={
        201: {
            "description": "The generated document was archived or an idempotent prior archive "
            "record was returned."
        },
        400: {"description": "The archive request is malformed or fails metadata validation."},
        401: {"description": "Required caller context is missing."},
        403: {"description": "The caller is not authorized to archive documents."},
        409: {
            "description": "The archive request id was reused with different content or metadata."
        },
    },
)
async def create_document(
    request_body: ArchiveDocumentCreateRequest,
    service: ArchiveDocumentService = Depends(archive_service),
    context: CallerContext = Depends(caller_context),
    request_trace_id: str = Depends(trace_id),
) -> ArchiveDocumentResponse:
    metadata = service.create_document(
        request=request_body,
        caller_context=context,
        trace_id=request_trace_id,
    )
    return ArchiveDocumentResponse.from_metadata(metadata)


@router.get(
    "/{document_id}",
    response_model=ArchiveDocumentResponse,
    summary="Get archived document metadata",
    description=(
        "Returns support-safe archived document metadata after caller-context validation, "
        "authorization, and access-audit recording. Storage keys and internal object paths are "
        "not exposed."
    ),
    responses={
        200: {"description": "Archived document metadata."},
        401: {"description": "Required caller context is missing."},
        403: {"description": "The caller is not authorized to read document metadata."},
        404: {"description": "The document does not exist."},
    },
)
async def get_document(
    document_id: str,
    service: ArchiveDocumentService = Depends(archive_service),
    context: CallerContext = Depends(caller_context),
    request_trace_id: str = Depends(trace_id),
) -> ArchiveDocumentResponse:
    metadata = service.get_document_metadata(
        document_id=document_id,
        caller_context=context,
        trace_id=request_trace_id,
    )
    return ArchiveDocumentResponse.from_metadata(metadata)


@router.get(
    "/{document_id}/download",
    summary="Download an archived document",
    description=(
        "Returns the archived document binary only after caller-context validation, authorization, "
        "object retrieval, checksum verification, and access-audit recording."
    ),
    responses={
        200: {"description": "Archived document binary."},
        401: {"description": "Required caller context is missing."},
        403: {"description": "The caller is not authorized to download the document."},
        404: {"description": "The document metadata or binary was not found."},
        409: {"description": "The stored binary failed checksum verification."},
    },
)
async def download_document(
    document_id: str,
    service: ArchiveDocumentService = Depends(archive_service),
    context: CallerContext = Depends(caller_context),
    request_trace_id: str = Depends(trace_id),
) -> Response:
    metadata, content = service.get_document_binary(
        document_id=document_id,
        caller_context=context,
        trace_id=request_trace_id,
    )
    return Response(
        content=content,
        media_type=metadata.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{metadata.document_id}.{metadata.output_format}"',
            "X-Document-Checksum-Algorithm": metadata.checksum_algorithm,
            "X-Document-Checksum": metadata.checksum,
        },
    )


@router.get(
    "/{document_id}/access-events",
    response_model=AccessEventListResponse,
    summary="List document access events",
    description=(
        "Returns audit events recorded for one archived document. This endpoint is for support "
        "and operator investigation, not customer-facing document access."
    ),
    responses={
        200: {"description": "Access-audit events for the document."},
        401: {"description": "Required caller context is missing."},
        403: {"description": "The caller is not authorized to read access-audit events."},
        404: {"description": "The document does not exist."},
    },
)
async def list_access_events(
    document_id: str,
    service: ArchiveDocumentService = Depends(archive_service),
    context: CallerContext = Depends(caller_context),
    request_trace_id: str = Depends(trace_id),
) -> AccessEventListResponse:
    events = service.list_access_events(
        document_id=document_id,
        caller_context=context,
        trace_id=request_trace_id,
    )
    return AccessEventListResponse(document_id=document_id, events=events)
