from base64 import b64encode
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from fastapi import Request
import pytest

from app.archive.api import archive_service, build_default_archive_service
from app.archive.api_models import ArchiveDocumentCreateRequest
from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import AccessEventType, AuthorizationDecision, InMemoryAccessAuditRepository
from app.archive.authorization import AuthorizationFailedError
from app.archive.exceptions import (
    DocumentChecksumMismatchError,
    DocumentNotFoundError,
    MetadataValidationError,
    StorageReadFailedError,
)
from app.archive.repository import InMemoryArchiveDocumentRepository
from app.archive.service import ArchiveDocumentService
from app.archive.storage import FilesystemObjectStorage
from app.security.caller_context import CallerContext
from tests.unit.test_archive_writer import valid_metadata_input


def _service(tmp_path: Path) -> ArchiveDocumentService:
    repository = InMemoryArchiveDocumentRepository()
    storage = FilesystemObjectStorage(tmp_path / "objects")
    return ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=InMemoryAccessAuditRepository(),
    )


def _create_request(content: bytes = b"portfolio review pdf bytes") -> ArchiveDocumentCreateRequest:
    return ArchiveDocumentCreateRequest(
        metadata=valid_metadata_input(),
        content_base64=b64encode(content).decode("ascii"),
    )


def _caller(caller_service: str = "lotus-report") -> CallerContext:
    return CallerContext(
        caller_service=caller_service,
        actor_type="service",
        actor_id="report-worker",
        correlation_id="corr-service",
    )


def test_create_document_records_archive_create_audit_event(tmp_path: Path) -> None:
    service = _service(tmp_path)

    metadata = service.create_document(
        request=_create_request(),
        caller_context=_caller(),
        trace_id="trace-create",
    )

    events = service.audit_repository.list_by_document_id(metadata.document_id)
    assert [event.event_type for event in events] == [AccessEventType.ARCHIVE_CREATE]
    assert events[0].authorization_decision == AuthorizationDecision.ALLOWED


def test_create_document_rejects_invalid_base64_content(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(MetadataValidationError):
        service.create_document(
            request=ArchiveDocumentCreateRequest(
                metadata=valid_metadata_input(),
                content_base64="not-valid-base64",
            ),
            caller_context=_caller(),
            trace_id="trace-invalid",
        )


def test_unauthorized_create_records_denied_audit_event(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(AuthorizationFailedError):
        service.create_document(
            request=_create_request(),
            caller_context=_caller(caller_service="lotus-workbench"),
            trace_id="trace-denied",
        )

    events = service.audit_repository.list_by_document_id(None)
    assert [event.event_type for event in events] == [AccessEventType.AUTHORIZATION_DENIED]
    assert events[0].authorization_decision == AuthorizationDecision.DENIED


def test_metadata_lookup_records_access_audit_event(tmp_path: Path) -> None:
    service = _service(tmp_path)
    metadata = service.create_document(
        request=_create_request(),
        caller_context=_caller(),
        trace_id="trace-create",
    )

    returned = service.get_document_metadata(
        document_id=metadata.document_id,
        caller_context=_caller(caller_service="lotus-gateway"),
        trace_id="trace-read",
    )

    assert returned == metadata
    events = service.audit_repository.list_by_document_id(metadata.document_id)
    assert [event.event_type for event in events] == [
        AccessEventType.ARCHIVE_CREATE,
        AccessEventType.METADATA_READ,
    ]


def test_download_detects_missing_binary(tmp_path: Path) -> None:
    service = _service(tmp_path)
    metadata = service.create_document(
        request=_create_request(),
        caller_context=_caller(),
        trace_id="trace-create",
    )
    (tmp_path / "objects" / metadata.storage_key).unlink()

    with pytest.raises(StorageReadFailedError):
        service.get_document_binary(
            document_id=metadata.document_id,
            caller_context=_caller(caller_service="lotus-gateway"),
            trace_id="trace-download",
        )


def test_download_detects_checksum_mismatch(tmp_path: Path) -> None:
    service = _service(tmp_path)
    metadata = service.create_document(
        request=_create_request(),
        caller_context=_caller(),
        trace_id="trace-create",
    )
    (tmp_path / "objects" / metadata.storage_key).write_bytes(b"corrupted")

    with pytest.raises(DocumentChecksumMismatchError):
        service.get_document_binary(
            document_id=metadata.document_id,
            caller_context=_caller(caller_service="lotus-gateway"),
            trace_id="trace-download",
        )


def test_unknown_document_raises_not_found(tmp_path: Path) -> None:
    service = _service(tmp_path)

    with pytest.raises(DocumentNotFoundError):
        service.get_document_metadata(
            document_id="doc_missing",
            caller_context=_caller(caller_service="lotus-gateway"),
            trace_id="trace-missing",
        )


def test_default_archive_service_factory_builds_service() -> None:
    service = build_default_archive_service()

    assert isinstance(service, ArchiveDocumentService)


def test_archive_service_dependency_caches_default_service() -> None:
    request = cast(Request, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())))

    first = archive_service(request)
    second = archive_service(request)

    assert second is first
