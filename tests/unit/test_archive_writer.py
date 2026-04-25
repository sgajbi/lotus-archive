from datetime import date
from pathlib import Path

import pytest

from app.archive.archive_writer import ArchiveWriter
from app.archive.exceptions import DuplicateArchiveRequestConflict
from app.archive.models import ArchiveDocumentInput, DocumentClassification
from app.archive.repository import InMemoryArchiveDocumentRepository
from app.archive.storage import FilesystemObjectStorage


def valid_metadata_input(**overrides: object) -> ArchiveDocumentInput:
    values: dict[str, object] = {
        "archive_request_id": "archive-request-001",
        "report_job_id": "report-job-001",
        "report_request_id": "report-request-001",
        "snapshot_id": "snapshot-001",
        "render_job_id": "render-job-001",
        "render_attempt_id": "render-attempt-001",
        "report_type": "portfolio_review",
        "portfolio_scope": "single_portfolio",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "client_reference": "client-ref-001",
        "as_of_date": date(2026, 4, 25),
        "reporting_period_start": date(2026, 1, 1),
        "reporting_period_end": date(2026, 3, 31),
        "frequency": "quarterly",
        "template_id": "portfolio-review",
        "template_version": "v1",
        "render_service_version": "0.1.0",
        "report_data_contract_version": "rfc-0101-v1",
        "mime_type": "application/pdf",
        "output_format": "pdf",
        "classification": DocumentClassification.CONFIDENTIAL,
        "region": "SG",
        "tenant_id": "tenant-private-bank",
        "retention_policy_id": "generated-report-standard",
        "retention_start_date": date(2026, 4, 25),
        "retain_until_date": date(2033, 4, 25),
        "created_by_service": "lotus-report",
        "created_by_actor": "report-worker",
    }
    values.update(overrides)
    return ArchiveDocumentInput.model_validate(values)


def _writer(tmp_path: Path) -> ArchiveWriter:
    return ArchiveWriter(
        repository=InMemoryArchiveDocumentRepository(),
        storage=FilesystemObjectStorage(tmp_path / "objects"),
    )


def test_archive_writer_persists_metadata_and_binary_behind_storage_abstraction(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path)
    metadata_input = valid_metadata_input()
    content = b"portfolio review pdf bytes"

    metadata = writer.archive_document(metadata_input=metadata_input, content=content)

    assert metadata.document_id.startswith("doc_")
    assert metadata.storage_provider == "filesystem"
    assert metadata.storage_namespace == "local-development"
    assert metadata.storage_key.startswith("sg/tenant-private-bank/portfolio_review/doc_")
    assert metadata.checksum_algorithm == "sha256"
    assert metadata.size_bytes == len(content)
    assert (tmp_path / "objects" / metadata.storage_key).read_bytes() == content


def test_archive_writer_duplicate_request_is_idempotent(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    metadata_input = valid_metadata_input()
    content = b"same rendered artifact"

    first = writer.archive_document(metadata_input=metadata_input, content=content)
    second = writer.archive_document(metadata_input=metadata_input, content=content)

    assert second == first


def test_archive_writer_rejects_duplicate_request_with_different_content(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path)
    metadata_input = valid_metadata_input()
    writer.archive_document(metadata_input=metadata_input, content=b"original")

    with pytest.raises(DuplicateArchiveRequestConflict):
        writer.archive_document(metadata_input=metadata_input, content=b"changed")


def test_archive_writer_rejects_duplicate_request_with_different_metadata(
    tmp_path: Path,
) -> None:
    writer = _writer(tmp_path)
    original = valid_metadata_input()
    changed = valid_metadata_input(report_job_id="report-job-002")
    content = b"same content"
    writer.archive_document(metadata_input=original, content=content)

    with pytest.raises(DuplicateArchiveRequestConflict):
        writer.archive_document(metadata_input=changed, content=content)


def test_archive_writer_uses_support_safe_unspecified_tenant_segment(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    metadata_input = valid_metadata_input(tenant_id=None)

    metadata = writer.archive_document(metadata_input=metadata_input, content=b"content")

    assert "/tenant-unspecified/" in metadata.storage_key
