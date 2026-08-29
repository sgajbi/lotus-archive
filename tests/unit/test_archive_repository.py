from datetime import datetime, timezone

import pytest

from app.archive.exceptions import DuplicateArchiveRequestConflict, HistoricalIntegrityError
from app.archive.models import (
    MUTABLE_DOCUMENT_FIELDS,
    ArchiveDocumentMetadata,
    LegalHoldStatus,
    PurgeStatus,
)
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


def test_in_memory_save_refuses_to_change_immutable_fields() -> None:
    """Historical integrity: identity, provenance and scope never move after archival."""
    repository = InMemoryArchiveDocumentRepository()
    metadata = _metadata("doc_immutability", "req-immutability")
    repository.save(metadata)

    tampered = metadata.model_copy(update={"checksum": "b" * 64, "tenant_id": "tenant-other"})
    with pytest.raises(HistoricalIntegrityError) as excinfo:
        repository.save(tampered)
    assert "checksum" in str(excinfo.value)
    assert "tenant_id" in str(excinfo.value)
    assert repository.get_by_document_id(metadata.document_id) == metadata


def test_in_memory_save_allows_every_governed_posture_mutation() -> None:
    """The full mutable set is writable; anything narrower would break purge and lifecycle."""
    repository = InMemoryArchiveDocumentRepository()
    metadata = _metadata("doc_immutability", "req-immutability")
    repository.save(metadata)

    now = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    updated = metadata.model_copy(
        update={
            "purge_status": PurgeStatus.ELIGIBLE,
            "purge_eligible_at": now,
            "legal_hold_status": LegalHoldStatus.ACTIVE,
            "legal_hold_count": 2,
            "superseded_by_document_id": "doc_new",
            "updated_at": now,
        }
    )
    repository.save(updated)
    assert repository.get_by_document_id(metadata.document_id) == updated


def test_mutable_field_registry_matches_what_the_service_actually_mutates() -> None:
    """Fitness function: every field the service mutates via model_copy must be registered.

    If a new service flow mutates an unregistered field, both repositories will refuse the
    write at runtime - this test turns that into a build-time failure with a pointed message.
    """
    import re
    from pathlib import Path

    service_source = (
        Path(__file__).resolve().parents[2] / "src" / "app" / "archive" / "service.py"
    ).read_text(encoding="utf-8")
    mutated: set[str] = set()
    for block in re.findall(r"model_copy\(\s*update=\{(.*?)\}", service_source, re.S):
        mutated.update(re.findall(r'"([a-z_]+)":', block))
    for assignment in re.findall(r'target_updates\["([a-z_]+)"\]', service_source):
        mutated.add(assignment)
    document_fields = set(ArchiveDocumentMetadata.model_fields)
    mutated_document_fields = mutated & document_fields

    unregistered = sorted(mutated_document_fields - MUTABLE_DOCUMENT_FIELDS)
    assert unregistered == [], (
        "service.py mutates document fields that MUTABLE_DOCUMENT_FIELDS does not register; "
        f"both repositories will refuse those writes at runtime: {unregistered}"
    )
