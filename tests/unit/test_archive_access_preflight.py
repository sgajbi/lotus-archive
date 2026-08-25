from base64 import b64encode
from pathlib import Path

import pytest

from app.archive.access_preflight import (
    ArchiveAccessResultState,
    ArchiveAccessPreflightItem,
    ArchiveAccessReasonCode,
    ArchiveAccessState,
    result_state_for_items,
)
from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import InMemoryAccessAuditRepository
from app.archive.exceptions import (
    ArchiveDocumentLookupTimeoutError,
    ArchiveDocumentLookupUnavailableError,
)
from app.archive.repository import (
    ArchiveDocumentBatchLookup,
    InMemoryArchiveDocumentRepository,
)
from app.archive.service import ArchiveDocumentService
from app.archive.authorization import AuthorizationFailedError
from app.archive.commands import ArchiveDocumentCreateCommand
from app.archive.storage import FilesystemObjectStorage
from app.security.caller_context import CallerContext, CallerScopeMissingError
from tests.unit.test_archive_writer import valid_metadata_input


class CountingArchiveRepository(InMemoryArchiveDocumentRepository):
    def __init__(self) -> None:
        super().__init__()
        self.batch_lookups: list[tuple[str, ...]] = []

    def get_by_document_ids(
        self,
        document_ids: tuple[str, ...],
    ) -> ArchiveDocumentBatchLookup:
        self.batch_lookups.append(document_ids)
        return super().get_by_document_ids(document_ids)


class PartialArchiveRepository(CountingArchiveRepository):
    def __init__(self, unavailable_document_id: str) -> None:
        super().__init__()
        self.unavailable_document_id = unavailable_document_id

    def get_by_document_ids(
        self,
        document_ids: tuple[str, ...],
    ) -> ArchiveDocumentBatchLookup:
        self.batch_lookups.append(document_ids)
        result = InMemoryArchiveDocumentRepository.get_by_document_ids(self, document_ids)
        return ArchiveDocumentBatchLookup(
            documents=result.documents,
            unavailable_document_ids=frozenset({self.unavailable_document_id}),
        )


class UnavailableArchiveRepository(CountingArchiveRepository):
    def get_by_document_ids(
        self,
        document_ids: tuple[str, ...],
    ) -> ArchiveDocumentBatchLookup:
        self.batch_lookups.append(document_ids)
        raise ArchiveDocumentLookupUnavailableError("archive lookup unavailable")


class TimedOutArchiveRepository(UnavailableArchiveRepository):
    def get_by_document_ids(
        self,
        document_ids: tuple[str, ...],
    ) -> ArchiveDocumentBatchLookup:
        self.batch_lookups.append(document_ids)
        raise ArchiveDocumentLookupTimeoutError("archive lookup deadline exceeded")


def _caller(
    *,
    caller_service: str = "lotus-gateway",
    tenant_id: str | None = "tenant-private-bank",
    region: str | None = "SG",
) -> CallerContext:
    return CallerContext(
        caller_service=caller_service,
        actor_type="service",
        actor_id="gateway-worker",
        correlation_id="corr-preflight",
        tenant_id=tenant_id,
        region=region,
    )


def _service(
    tmp_path: Path,
    repository: InMemoryArchiveDocumentRepository,
) -> ArchiveDocumentService:
    storage = FilesystemObjectStorage(tmp_path / "objects")
    return ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=InMemoryAccessAuditRepository(),
    )


def _create_document(
    service: ArchiveDocumentService,
    *,
    archive_request_id: str,
    tenant_id: str | None = "tenant-private-bank",
    region: str = "SG",
) -> str:
    metadata = valid_metadata_input(
        archive_request_id=archive_request_id,
        report_job_id=f"report-job-{archive_request_id}",
        render_job_id=f"render-job-{archive_request_id}",
        render_attempt_id=f"render-attempt-{archive_request_id}",
        tenant_id=tenant_id,
        region=region,
    )
    created = service.create_document(
        command=ArchiveDocumentCreateCommand(
            metadata=metadata,
            content_base64=b64encode(b"preflight document").decode("ascii"),
        ),
        caller_context=_caller(caller_service="lotus-report"),
        trace_id="trace-create",
    )
    return created.document_id


def test_preflight_uses_one_lookup_and_preserves_order_and_scope_redaction(
    tmp_path: Path,
) -> None:
    repository = CountingArchiveRepository()
    service = _service(tmp_path, repository)
    allowed_id = _create_document(service, archive_request_id="preflight-allowed")
    denied_id = _create_document(
        service,
        archive_request_id="preflight-denied",
        tenant_id="tenant-other",
        region="EMEA",
    )

    result = service.preflight_document_access(
        document_ids=(denied_id, "doc_missing", allowed_id),
        caller_context=_caller(),
        trace_id="trace-preflight",
    )

    assert repository.batch_lookups == [(denied_id, "doc_missing", allowed_id)]
    assert [item.document_id for item in result.items] == [denied_id, "doc_missing", allowed_id]
    assert [item.state for item in result.items] == [
        ArchiveAccessState.DENIED,
        ArchiveAccessState.MISSING,
        ArchiveAccessState.ALLOWED,
    ]
    assert result.result_state is ArchiveAccessResultState.COMPLETE
    assert all("storage" not in item.reason_code.value for item in result.items)


def test_preflight_reports_partial_lookup_without_fanout(tmp_path: Path) -> None:
    repository = PartialArchiveRepository("doc_unavailable")
    service = _service(tmp_path, repository)

    result = service.preflight_document_access(
        document_ids=("doc_allowed", "doc_unavailable"),
        caller_context=_caller(),
        trace_id="trace-preflight-partial",
    )

    assert repository.batch_lookups == [("doc_allowed", "doc_unavailable")]
    assert result.result_state is ArchiveAccessResultState.PARTIAL
    assert [item.state for item in result.items] == [
        ArchiveAccessState.MISSING,
        ArchiveAccessState.UNAVAILABLE,
    ]


def test_preflight_fails_closed_when_archive_lookup_is_unavailable(tmp_path: Path) -> None:
    repository = UnavailableArchiveRepository()
    service = _service(tmp_path, repository)

    result = service.preflight_document_access(
        document_ids=("doc_one", "doc_two"),
        caller_context=_caller(),
        trace_id="trace-preflight-unavailable",
    )

    assert result.result_state is ArchiveAccessResultState.UNAVAILABLE
    assert all(item.state is ArchiveAccessState.UNAVAILABLE for item in result.items)
    assert all(item.reason_code.value == "lookup_unavailable" for item in result.items)


def test_preflight_maps_archive_lookup_timeout_to_unavailable(tmp_path: Path) -> None:
    repository = TimedOutArchiveRepository()
    service = _service(tmp_path, repository)

    result = service.preflight_document_access(
        document_ids=("doc_timed_out",),
        caller_context=_caller(),
        trace_id="trace-preflight-timeout",
    )

    assert repository.batch_lookups == [("doc_timed_out",)]
    assert result.result_state is ArchiveAccessResultState.UNAVAILABLE
    assert result.items[0].reason_code.value == "lookup_unavailable"


def test_result_state_is_unavailable_when_every_item_is_unavailable() -> None:
    items = (
        ArchiveAccessPreflightItem(
            document_id="doc_one",
            state=ArchiveAccessState.UNAVAILABLE,
            reason_code=ArchiveAccessReasonCode.LOOKUP_UNAVAILABLE,
        ),
    )

    assert result_state_for_items(items) is ArchiveAccessResultState.UNAVAILABLE


def test_preflight_requires_tenant_and_region_scope(tmp_path: Path) -> None:
    service = _service(tmp_path, CountingArchiveRepository())

    with pytest.raises(CallerScopeMissingError):
        service.preflight_document_access(
            document_ids=("doc_one",),
            caller_context=_caller(tenant_id=None, region=None),
            trace_id="trace-preflight-missing-scope",
        )


def test_single_document_metadata_denies_scope_mismatch_before_publication(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, CountingArchiveRepository())
    document_id = _create_document(service, archive_request_id="single-scope")

    with pytest.raises(AuthorizationFailedError):
        service.get_document_metadata(
            document_id=document_id,
            caller_context=_caller(tenant_id="tenant-other", region="EMEA"),
            trace_id="trace-single-scope",
        )
