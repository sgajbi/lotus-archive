from base64 import b64encode
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from fastapi import Request
import pytest

from app.archive.api import archive_service, build_default_archive_service
from app.archive.api_models import ArchiveDocumentCreateRequest, LegalHoldCreateRequest
from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import AccessEventType, AuthorizationDecision, InMemoryAccessAuditRepository
from app.archive.authorization import AuthorizationFailedError
from app.archive.exceptions import (
    DocumentChecksumMismatchError,
    DocumentNotFoundError,
    LegalHoldActiveError,
    LegalHoldNotFoundError,
    MetadataValidationError,
    PurgeNotEligibleError,
    StorageReadFailedError,
)
from app.archive.models import LegalHoldStatus, PurgeStatus
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


def test_purge_evaluation_marks_document_eligible_after_retention_date(tmp_path: Path) -> None:
    service = _service(tmp_path)
    metadata = service.create_document(
        request=_create_request(),
        caller_context=_caller(),
        trace_id="trace-create",
    )

    metadata, purge_eligible, reason_code = service.evaluate_purge(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="trace-eval",
        evaluation_date=metadata.retain_until_date,
    )

    assert purge_eligible is True
    assert reason_code == "retention_elapsed"
    assert metadata.purge_status == PurgeStatus.ELIGIBLE
    events = service.audit_repository.list_by_document_id(metadata.document_id)
    assert AccessEventType.PURGE_EVALUATION in [event.event_type for event in events]


def test_purge_evaluation_blocks_active_retention_period(tmp_path: Path) -> None:
    service = _service(tmp_path)
    metadata = service.create_document(
        request=_create_request(),
        caller_context=_caller(),
        trace_id="trace-create",
    )

    metadata, purge_eligible, reason_code = service.evaluate_purge(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="trace-eval",
        evaluation_date=metadata.retention_start_date,
    )

    assert purge_eligible is False
    assert reason_code == "retention_period_active"
    assert metadata.purge_status == PurgeStatus.NOT_ELIGIBLE


def test_legal_hold_blocks_purge_until_released(tmp_path: Path) -> None:
    service = _service(tmp_path)
    metadata = service.create_document(
        request=_create_request(),
        caller_context=_caller(),
        trace_id="trace-create",
    )
    legal_hold = service.set_legal_hold(
        document_id=metadata.document_id,
        request=LegalHoldCreateRequest(
            hold_reason="Regulatory review",
            authority_reference="CASE-001",
        ),
        caller_context=_caller(),
        trace_id="trace-hold",
    )

    with pytest.raises(LegalHoldActiveError):
        service.purge_document(
            document_id=metadata.document_id,
            caller_context=_caller(),
            trace_id="trace-purge-blocked",
            evaluation_date=metadata.retain_until_date,
        )

    released = service.release_legal_hold(
        document_id=metadata.document_id,
        legal_hold_id=legal_hold.legal_hold_id,
        release_reason="Review complete",
        caller_context=_caller(),
        trace_id="trace-release",
    )
    purged, reason_code = service.purge_document(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="trace-purge",
        evaluation_date=metadata.retain_until_date,
    )

    assert released.hold_status == LegalHoldStatus.CLEAR
    assert purged.purge_status == PurgeStatus.PURGED
    assert purged.purged_at is not None
    assert reason_code == "purged"
    assert not (tmp_path / "objects" / metadata.storage_key).exists()


def test_purge_is_idempotent_after_first_execution(tmp_path: Path) -> None:
    service = _service(tmp_path)
    metadata = service.create_document(
        request=_create_request(),
        caller_context=_caller(),
        trace_id="trace-create",
    )
    first, first_reason = service.purge_document(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="trace-purge",
        evaluation_date=metadata.retain_until_date,
    )
    second, second_reason = service.purge_document(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="trace-purge-again",
        evaluation_date=metadata.retain_until_date,
    )

    assert first.purge_status == PurgeStatus.PURGED
    assert first_reason == "purged"
    assert second.purge_status == PurgeStatus.PURGED
    assert second_reason == "already_purged"


def test_purge_rejects_document_still_under_retention(tmp_path: Path) -> None:
    service = _service(tmp_path)
    metadata = service.create_document(
        request=_create_request(),
        caller_context=_caller(),
        trace_id="trace-create",
    )

    with pytest.raises(PurgeNotEligibleError):
        service.purge_document(
            document_id=metadata.document_id,
            caller_context=_caller(),
            trace_id="trace-purge",
            evaluation_date=metadata.retention_start_date,
        )


def test_release_unknown_legal_hold_reports_not_found(tmp_path: Path) -> None:
    service = _service(tmp_path)
    metadata = service.create_document(
        request=_create_request(),
        caller_context=_caller(),
        trace_id="trace-create",
    )

    with pytest.raises(LegalHoldNotFoundError):
        service.release_legal_hold(
            document_id=metadata.document_id,
            legal_hold_id="hold_missing",
            release_reason="No longer needed",
            caller_context=_caller(),
            trace_id="trace-release",
        )
