from __future__ import annotations

from pathlib import Path
import tempfile

from fastapi import APIRouter, Depends, Request, Response, status

from app.archive.api_models import (
    AccessEventListResponse,
    ArchiveDocumentCreateRequest,
    ArchiveDocumentResponse,
    LegalHoldCreateRequest,
    LegalHoldReleaseRequest,
    LegalHoldResponse,
    LifecycleRelationshipResponse,
    LifecycleTransitionRequest,
    PurgeEvaluationResponse,
    PurgeExecutionResponse,
    RetentionResponse,
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
    "/{document_id}/current",
    response_model=ArchiveDocumentResponse,
    summary="Get current document in lifecycle",
    description=(
        "Returns the current archived document after following supersession, correction, and "
        "reissue relationships. Historical document metadata remains available through the "
        "standard metadata endpoint."
    ),
    responses={
        200: {"description": "Current archived document metadata."},
        401: {"description": "Required caller context is missing."},
        403: {"description": "The caller is not authorized to read document metadata."},
        404: {"description": "The document does not exist."},
        409: {"description": "The lifecycle relationship chain is inconsistent."},
    },
)
async def get_current_document(
    document_id: str,
    service: ArchiveDocumentService = Depends(archive_service),
    context: CallerContext = Depends(caller_context),
    request_trace_id: str = Depends(trace_id),
) -> ArchiveDocumentResponse:
    metadata = service.get_current_document_metadata(
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


@router.get(
    "/{document_id}/retention",
    response_model=RetentionResponse,
    summary="Get document retention posture",
    description=(
        "Returns the archived document retention, purge, and legal-hold posture for support and "
        "operations. The response is support-safe and does not expose object-storage paths."
    ),
    responses={
        200: {"description": "Retention and legal-hold posture for the document."},
        401: {"description": "Required caller context is missing."},
        403: {"description": "The caller is not authorized to read retention posture."},
        404: {"description": "The document does not exist."},
    },
)
async def get_retention(
    document_id: str,
    service: ArchiveDocumentService = Depends(archive_service),
    context: CallerContext = Depends(caller_context),
    request_trace_id: str = Depends(trace_id),
) -> RetentionResponse:
    metadata = service.get_retention(
        document_id=document_id,
        caller_context=context,
        trace_id=request_trace_id,
    )
    return RetentionResponse.from_metadata(metadata)


@router.post(
    "/{document_id}/purge-evaluation",
    response_model=PurgeEvaluationResponse,
    summary="Evaluate document purge eligibility",
    description=(
        "Evaluates whether retention has elapsed and no active legal hold blocks purge. This "
        "action records audit evidence but does not delete document binary content."
    ),
    responses={
        200: {"description": "Purge eligibility evaluation result."},
        401: {"description": "Required caller context is missing."},
        403: {"description": "The caller is not authorized to evaluate purge."},
        404: {"description": "The document does not exist."},
    },
)
async def evaluate_purge(
    document_id: str,
    service: ArchiveDocumentService = Depends(archive_service),
    context: CallerContext = Depends(caller_context),
    request_trace_id: str = Depends(trace_id),
) -> PurgeEvaluationResponse:
    metadata, purge_eligible, reason_code = service.evaluate_purge(
        document_id=document_id,
        caller_context=context,
        trace_id=request_trace_id,
    )
    return PurgeEvaluationResponse(
        **RetentionResponse.from_metadata(metadata).model_dump(),
        purge_eligible=purge_eligible,
        reason_code=reason_code,
    )


@router.post(
    "/{document_id}/purge",
    response_model=PurgeExecutionResponse,
    summary="Execute document purge",
    description=(
        "Executes a governed purge only when retention has elapsed and no legal hold is active. "
        "The action removes the stored binary through the archive storage abstraction and leaves "
        "support-safe metadata and audit evidence."
    ),
    responses={
        200: {"description": "Purge execution result."},
        401: {"description": "Required caller context is missing."},
        403: {"description": "The caller is not authorized to execute purge."},
        404: {"description": "The document does not exist."},
        409: {"description": "The document is not purge eligible or legal hold blocks purge."},
    },
)
async def purge_document(
    document_id: str,
    service: ArchiveDocumentService = Depends(archive_service),
    context: CallerContext = Depends(caller_context),
    request_trace_id: str = Depends(trace_id),
) -> PurgeExecutionResponse:
    metadata, reason_code = service.purge_document(
        document_id=document_id,
        caller_context=context,
        trace_id=request_trace_id,
    )
    return PurgeExecutionResponse(
        **RetentionResponse.from_metadata(metadata).model_dump(),
        purged=True,
        reason_code=reason_code,
    )


@router.post(
    "/{document_id}/legal-holds",
    status_code=status.HTTP_201_CREATED,
    response_model=LegalHoldResponse,
    summary="Set a document legal hold",
    description=(
        "Sets a legal hold on an archived document with a reason and authority reference. Active "
        "legal holds block purge regardless of retention eligibility."
    ),
    responses={
        201: {"description": "Legal hold was set."},
        401: {"description": "Required caller context is missing."},
        403: {"description": "The caller is not authorized to set legal holds."},
        404: {"description": "The document does not exist."},
    },
)
async def set_legal_hold(
    document_id: str,
    request_body: LegalHoldCreateRequest,
    service: ArchiveDocumentService = Depends(archive_service),
    context: CallerContext = Depends(caller_context),
    request_trace_id: str = Depends(trace_id),
) -> LegalHoldResponse:
    legal_hold = service.set_legal_hold(
        document_id=document_id,
        request=request_body,
        caller_context=context,
        trace_id=request_trace_id,
    )
    return LegalHoldResponse.from_record(legal_hold)


@router.delete(
    "/{document_id}/legal-holds/{legal_hold_id}",
    response_model=LegalHoldResponse,
    summary="Release a document legal hold",
    description=(
        "Releases an active legal hold and refreshes the document purge-blocking posture. The "
        "release is idempotent for already released holds and is recorded in access audit."
    ),
    responses={
        200: {"description": "Legal hold release result."},
        401: {"description": "Required caller context is missing."},
        403: {"description": "The caller is not authorized to release legal holds."},
        404: {"description": "The document or legal hold does not exist."},
    },
)
async def release_legal_hold(
    document_id: str,
    legal_hold_id: str,
    request_body: LegalHoldReleaseRequest,
    service: ArchiveDocumentService = Depends(archive_service),
    context: CallerContext = Depends(caller_context),
    request_trace_id: str = Depends(trace_id),
) -> LegalHoldResponse:
    legal_hold = service.release_legal_hold(
        document_id=document_id,
        legal_hold_id=legal_hold_id,
        release_reason=request_body.release_reason,
        caller_context=context,
        trace_id=request_trace_id,
    )
    return LegalHoldResponse.from_record(legal_hold)


@router.post(
    "/{document_id}/supersede",
    status_code=status.HTTP_201_CREATED,
    response_model=LifecycleRelationshipResponse,
    summary="Supersede an archived document",
    description=(
        "Records that another archived document supersedes this document. The historical document "
        "remains retrievable, the target document becomes current, and the lifecycle mutation is "
        "audited."
    ),
    responses={
        201: {"description": "Supersession relationship was recorded."},
        401: {"description": "Required caller context is missing."},
        403: {"description": "The caller is not authorized to manage lifecycle relationships."},
        404: {"description": "The source or target document does not exist."},
        409: {"description": "The lifecycle transition conflicts with existing document history."},
    },
)
async def supersede_document(
    document_id: str,
    request_body: LifecycleTransitionRequest,
    service: ArchiveDocumentService = Depends(archive_service),
    context: CallerContext = Depends(caller_context),
    request_trace_id: str = Depends(trace_id),
) -> LifecycleRelationshipResponse:
    relationship, current = service.supersede_document(
        document_id=document_id,
        request=request_body,
        caller_context=context,
        trace_id=request_trace_id,
    )
    return LifecycleRelationshipResponse.from_record(
        relationship,
        current_document_id=current.document_id,
    )


@router.post(
    "/{document_id}/correct",
    status_code=status.HTTP_201_CREATED,
    response_model=LifecycleRelationshipResponse,
    summary="Correct an archived document",
    description=(
        "Records that another archived document corrects this document. The historical document "
        "is preserved, the correction document becomes current, and the lifecycle mutation is "
        "audited."
    ),
    responses={
        201: {"description": "Correction relationship was recorded."},
        401: {"description": "Required caller context is missing."},
        403: {"description": "The caller is not authorized to manage lifecycle relationships."},
        404: {"description": "The source or target document does not exist."},
        409: {"description": "The lifecycle transition conflicts with existing document history."},
    },
)
async def correct_document(
    document_id: str,
    request_body: LifecycleTransitionRequest,
    service: ArchiveDocumentService = Depends(archive_service),
    context: CallerContext = Depends(caller_context),
    request_trace_id: str = Depends(trace_id),
) -> LifecycleRelationshipResponse:
    relationship, current = service.correct_document(
        document_id=document_id,
        request=request_body,
        caller_context=context,
        trace_id=request_trace_id,
    )
    return LifecycleRelationshipResponse.from_record(
        relationship,
        current_document_id=current.document_id,
    )


@router.post(
    "/{document_id}/reissue",
    status_code=status.HTTP_201_CREATED,
    response_model=LifecycleRelationshipResponse,
    summary="Reissue an archived document",
    description=(
        "Records that another archived document reissues this document. The historical document "
        "is preserved, the reissued document becomes current, and the lifecycle mutation is "
        "audited."
    ),
    responses={
        201: {"description": "Reissue relationship was recorded."},
        401: {"description": "Required caller context is missing."},
        403: {"description": "The caller is not authorized to manage lifecycle relationships."},
        404: {"description": "The source or target document does not exist."},
        409: {"description": "The lifecycle transition conflicts with existing document history."},
    },
)
async def reissue_document(
    document_id: str,
    request_body: LifecycleTransitionRequest,
    service: ArchiveDocumentService = Depends(archive_service),
    context: CallerContext = Depends(caller_context),
    request_trace_id: str = Depends(trace_id),
) -> LifecycleRelationshipResponse:
    relationship, current = service.reissue_document(
        document_id=document_id,
        request=request_body,
        caller_context=context,
        trace_id=request_trace_id,
    )
    return LifecycleRelationshipResponse.from_record(
        relationship,
        current_document_id=current.document_id,
    )
