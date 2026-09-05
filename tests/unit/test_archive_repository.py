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
from app.archive.models import LifecycleRelationshipRecord, LifecycleTransitionType
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


def _relationship(relationship_id: str = "lifecycle_1") -> LifecycleRelationshipRecord:
    return LifecycleRelationshipRecord(
        lifecycle_relationship_id=relationship_id,
        source_document_id="doc_1",
        target_document_id="doc_2",
        transition_type=LifecycleTransitionType.SUPERSEDE,
        transition_reason="Quarter-end correction",
        transition_reason_code="archive_document_supersession_requested",
        requested_by="operations-user",
    )


def test_in_memory_lifecycle_relationships_roundtrip_and_delete() -> None:
    repository = InMemoryArchiveDocumentRepository()
    saved = repository.save_lifecycle_relationship(_relationship())

    assert saved.lifecycle_relationship_id == "lifecycle_1"
    listed = repository.list_lifecycle_relationships("doc_1")
    assert [item.lifecycle_relationship_id for item in listed] == ["lifecycle_1"]

    repository.delete_lifecycle_relationship("lifecycle_1")
    assert repository.list_lifecycle_relationships("doc_1") == []
    # Deleting an unknown id is a no-op, never an error.
    repository.delete_lifecycle_relationship("lifecycle_missing")


def test_in_memory_lifecycle_transition_restores_source_when_target_save_fails() -> None:
    """The atomic unit: all three writes or none. When the target save
    fails, the already-written source is restored from the snapshot and
    the relationship is never recorded."""

    class _TargetRejectingRepository(InMemoryArchiveDocumentRepository):
        _fail_on: str | None = None

        def save(self, metadata: ArchiveDocumentMetadata) -> ArchiveDocumentMetadata:
            if self._fail_on == metadata.document_id:
                raise RuntimeError("target store unavailable")
            return super().save(metadata)

    repository = _TargetRejectingRepository()
    source = _metadata("doc_1", "archive-request-1")
    target = _metadata("doc_2", "archive-request-2")
    repository.save(source)
    repository.save(target)
    # The transition writes the source with its supersession pointer set;
    # after the target save fails, the ORIGINAL (pointer-free) source must
    # be back in place.
    updated_source = source.model_copy(update={"superseded_by_document_id": target.document_id})

    repository._fail_on = target.document_id
    with pytest.raises(RuntimeError, match="target store unavailable"):
        repository.apply_lifecycle_transition(
            updated_source,
            target,
            _relationship("lifecycle_rollback"),
        )

    restored = repository.get_by_document_id(source.document_id)
    assert restored is not None
    assert restored.superseded_by_document_id is None
    assert repository.list_lifecycle_relationships(source.document_id) == []
