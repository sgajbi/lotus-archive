from base64 import b64encode
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from fastapi import Request
import pytest

from app.archive.api import archive_service, build_default_archive_service
from app.archive.api_models import (
    ArchiveDocumentCreateRequest,
    LegalHoldCreateRequest,
    LifecycleTransitionRequest,
)
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
    SupersessionConflictError,
    UnsupportedLifecycleTransitionError,
)
from app.archive.models import LegalHoldStatus, LifecycleTransitionType, PurgeStatus
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


def _create_request_with_id(
    archive_request_id: str,
    *,
    content: bytes = b"portfolio review pdf bytes",
) -> ArchiveDocumentCreateRequest:
    return ArchiveDocumentCreateRequest(
        metadata=valid_metadata_input(
            archive_request_id=archive_request_id,
            report_job_id=f"report-job-{archive_request_id}",
            render_job_id=f"render-job-{archive_request_id}",
            render_attempt_id=f"render-attempt-{archive_request_id}",
        ),
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


def test_supersession_preserves_history_and_resolves_current_document(tmp_path: Path) -> None:
    service = _service(tmp_path)
    historical = service.create_document(
        request=_create_request_with_id("archive-request-historical"),
        caller_context=_caller(),
        trace_id="trace-create-old",
    )
    current = service.create_document(
        request=_create_request_with_id("archive-request-current"),
        caller_context=_caller(),
        trace_id="trace-create-new",
    )

    relationship, resolved = service.supersede_document(
        document_id=historical.document_id,
        request=LifecycleTransitionRequest(
            target_document_id=current.document_id,
            transition_reason="Quarterly report replaced by approved version",
        ),
        caller_context=_caller(),
        trace_id="trace-supersede",
    )

    historical_after = service.get_document_metadata(
        document_id=historical.document_id,
        caller_context=_caller(caller_service="lotus-gateway"),
        trace_id="trace-read-old",
    )
    current_after = service.get_current_document_metadata(
        document_id=historical.document_id,
        caller_context=_caller(caller_service="lotus-gateway"),
        trace_id="trace-current",
    )

    assert relationship.transition_type == LifecycleTransitionType.SUPERSEDE
    assert relationship.source_document_id == historical.document_id
    assert relationship.target_document_id == current.document_id
    assert resolved.document_id == current.document_id
    assert historical_after.document_id == historical.document_id
    assert historical_after.superseded_by_document_id == current.document_id
    assert current_after.document_id == current.document_id
    assert current_after.supersedes_document_id == historical.document_id
    relationships = service.repository.list_lifecycle_relationships(historical.document_id)
    assert [item.lifecycle_relationship_id for item in relationships] == [
        relationship.lifecycle_relationship_id
    ]
    event_types = [
        event.event_type
        for event in service.audit_repository.list_by_document_id(historical.document_id)
    ]
    assert AccessEventType.LIFECYCLE_SUPERSEDE in event_types
    assert AccessEventType.CURRENT_DOCUMENT_READ in event_types


def test_correction_and_reissue_set_explicit_lifecycle_semantics(tmp_path: Path) -> None:
    service = _service(tmp_path)
    source = service.create_document(
        request=_create_request_with_id("archive-request-source"),
        caller_context=_caller(),
        trace_id="trace-source",
    )
    correction = service.create_document(
        request=_create_request_with_id("archive-request-correction"),
        caller_context=_caller(),
        trace_id="trace-correction",
    )
    reissue_source = service.create_document(
        request=_create_request_with_id("archive-request-reissue-source"),
        caller_context=_caller(),
        trace_id="trace-reissue-source",
    )
    reissue = service.create_document(
        request=_create_request_with_id("archive-request-reissue"),
        caller_context=_caller(),
        trace_id="trace-reissue",
    )

    correction_relationship, _ = service.correct_document(
        document_id=source.document_id,
        request=LifecycleTransitionRequest(
            target_document_id=correction.document_id,
            transition_reason="Corrected valuation date",
        ),
        caller_context=_caller(),
        trace_id="trace-correct",
    )
    reissue_relationship, _ = service.reissue_document(
        document_id=reissue_source.document_id,
        request=LifecycleTransitionRequest(
            target_document_id=reissue.document_id,
            transition_reason="Client delivery reissue",
        ),
        caller_context=_caller(),
        trace_id="trace-reissue-link",
    )

    corrected = service.get_current_document_metadata(
        document_id=source.document_id,
        caller_context=_caller(caller_service="lotus-gateway"),
        trace_id="trace-current-correction",
    )
    reissued = service.get_current_document_metadata(
        document_id=reissue_source.document_id,
        caller_context=_caller(caller_service="lotus-gateway"),
        trace_id="trace-current-reissue",
    )

    assert correction_relationship.transition_type == LifecycleTransitionType.CORRECT
    assert reissue_relationship.transition_type == LifecycleTransitionType.REISSUE
    assert corrected.correction_of_document_id == source.document_id
    assert reissued.reissue_of_document_id == reissue_source.document_id


def test_lifecycle_transition_rejects_non_current_source(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = service.create_document(
        request=_create_request_with_id("archive-request-first"),
        caller_context=_caller(),
        trace_id="trace-first",
    )
    second = service.create_document(
        request=_create_request_with_id("archive-request-second"),
        caller_context=_caller(),
        trace_id="trace-second",
    )
    third = service.create_document(
        request=_create_request_with_id("archive-request-third"),
        caller_context=_caller(),
        trace_id="trace-third",
    )
    service.supersede_document(
        document_id=first.document_id,
        request=LifecycleTransitionRequest(
            target_document_id=second.document_id,
            transition_reason="First replacement",
        ),
        caller_context=_caller(),
        trace_id="trace-supersede",
    )

    with pytest.raises(SupersessionConflictError):
        service.supersede_document(
            document_id=first.document_id,
            request=LifecycleTransitionRequest(
                target_document_id=third.document_id,
                transition_reason="Invalid replacement",
            ),
            caller_context=_caller(),
            trace_id="trace-conflict",
        )


def test_lifecycle_transition_rejects_self_reference(tmp_path: Path) -> None:
    service = _service(tmp_path)
    metadata = service.create_document(
        request=_create_request_with_id("archive-request-self"),
        caller_context=_caller(),
        trace_id="trace-create",
    )

    with pytest.raises(UnsupportedLifecycleTransitionError):
        service.reissue_document(
            document_id=metadata.document_id,
            request=LifecycleTransitionRequest(
                target_document_id=metadata.document_id,
                transition_reason="Invalid self reissue",
            ),
            caller_context=_caller(),
            trace_id="trace-self",
        )


def test_lifecycle_transition_rejects_purged_documents(tmp_path: Path) -> None:
    service = _service(tmp_path)
    purged = service.create_document(
        request=_create_request_with_id("archive-request-purged"),
        caller_context=_caller(),
        trace_id="trace-purged",
    )
    target = service.create_document(
        request=_create_request_with_id("archive-request-target"),
        caller_context=_caller(),
        trace_id="trace-target",
    )
    service.purge_document(
        document_id=purged.document_id,
        caller_context=_caller(),
        trace_id="trace-purge",
        evaluation_date=purged.retain_until_date,
    )

    with pytest.raises(UnsupportedLifecycleTransitionError):
        service.supersede_document(
            document_id=purged.document_id,
            request=LifecycleTransitionRequest(
                target_document_id=target.document_id,
                transition_reason="Invalid purged source",
            ),
            caller_context=_caller(),
            trace_id="trace-lifecycle",
        )


def test_lifecycle_transition_rejects_historical_target(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = service.create_document(
        request=_create_request_with_id("archive-request-target-first"),
        caller_context=_caller(),
        trace_id="trace-first",
    )
    second = service.create_document(
        request=_create_request_with_id("archive-request-target-second"),
        caller_context=_caller(),
        trace_id="trace-second",
    )
    third = service.create_document(
        request=_create_request_with_id("archive-request-target-third"),
        caller_context=_caller(),
        trace_id="trace-third",
    )
    service.supersede_document(
        document_id=first.document_id,
        request=LifecycleTransitionRequest(
            target_document_id=second.document_id,
            transition_reason="First transition",
        ),
        caller_context=_caller(),
        trace_id="trace-supersede",
    )

    with pytest.raises(SupersessionConflictError):
        service.correct_document(
            document_id=third.document_id,
            request=LifecycleTransitionRequest(
                target_document_id=first.document_id,
                transition_reason="Historical target is invalid",
            ),
            caller_context=_caller(),
            trace_id="trace-conflict",
        )


def test_lifecycle_transition_rejects_target_with_existing_origin(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = service.create_document(
        request=_create_request_with_id("archive-request-origin-first"),
        caller_context=_caller(),
        trace_id="trace-first",
    )
    second = service.create_document(
        request=_create_request_with_id("archive-request-origin-second"),
        caller_context=_caller(),
        trace_id="trace-second",
    )
    third = service.create_document(
        request=_create_request_with_id("archive-request-origin-third"),
        caller_context=_caller(),
        trace_id="trace-third",
    )
    service.reissue_document(
        document_id=first.document_id,
        request=LifecycleTransitionRequest(
            target_document_id=second.document_id,
            transition_reason="First reissue",
        ),
        caller_context=_caller(),
        trace_id="trace-reissue",
    )

    with pytest.raises(SupersessionConflictError):
        service.supersede_document(
            document_id=third.document_id,
            request=LifecycleTransitionRequest(
                target_document_id=second.document_id,
                transition_reason="Target already has an origin",
            ),
            caller_context=_caller(),
            trace_id="trace-conflict",
        )


def test_current_document_resolution_detects_cycle(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = service.create_document(
        request=_create_request_with_id("archive-request-cycle-first"),
        caller_context=_caller(),
        trace_id="trace-first",
    )
    second = service.create_document(
        request=_create_request_with_id("archive-request-cycle-second"),
        caller_context=_caller(),
        trace_id="trace-second",
    )
    service.repository.save(
        first.model_copy(update={"superseded_by_document_id": second.document_id})
    )
    service.repository.save(
        second.model_copy(update={"superseded_by_document_id": first.document_id})
    )

    with pytest.raises(SupersessionConflictError):
        service.get_current_document_metadata(
            document_id=first.document_id,
            caller_context=_caller(caller_service="lotus-gateway"),
            trace_id="trace-current",
        )


def test_purge_evaluation_reports_missing_retention_date(tmp_path: Path) -> None:
    service = _service(tmp_path)
    metadata = service.create_document(
        request=ArchiveDocumentCreateRequest(
            metadata=valid_metadata_input(
                archive_request_id="archive-request-no-retention",
                retain_until_date=None,
            ),
            content_base64=b64encode(b"no retention").decode("ascii"),
        ),
        caller_context=_caller(),
        trace_id="trace-create",
    )

    metadata, purge_eligible, reason_code = service.evaluate_purge(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="trace-eval",
    )

    assert purge_eligible is False
    assert reason_code == "retain_until_date_missing"
    assert metadata.purge_status == PurgeStatus.NOT_ELIGIBLE
