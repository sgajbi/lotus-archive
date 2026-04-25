import pytest

from app.archive.exceptions import DuplicateArchiveRequestConflict
from app.archive.models import ArchiveDocumentMetadata
from app.archive.repository import InMemoryArchiveDocumentRepository
from tests.unit.test_archive_metadata_model import valid_metadata_input


def _metadata(document_id: str, archive_request_id: str) -> ArchiveDocumentMetadata:
    metadata_input = valid_metadata_input(archive_request_id=archive_request_id)
    return ArchiveDocumentMetadata(
        **metadata_input.model_dump(),
        document_id=document_id,
        storage_provider="filesystem",
        storage_namespace="local-development",
        storage_key=f"sg/tenant/report/{document_id}.pdf",
        checksum_algorithm="sha256",
        checksum="a" * 64,
        size_bytes=10,
    )


def test_in_memory_repository_returns_none_for_missing_records() -> None:
    repository = InMemoryArchiveDocumentRepository()

    assert repository.get_by_document_id("missing") is None
    assert repository.get_by_archive_request_id("missing") is None


def test_in_memory_repository_rejects_archive_request_collision() -> None:
    repository = InMemoryArchiveDocumentRepository()
    repository.save(_metadata("doc_1", "archive-request-1"))

    with pytest.raises(DuplicateArchiveRequestConflict):
        repository.save(_metadata("doc_2", "archive-request-1"))
