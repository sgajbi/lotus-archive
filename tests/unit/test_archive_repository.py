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


def test_in_memory_save_refuses_transition_owned_columns() -> None:
    """save() writes only `updated_at` on an existing row (issue #166).

    Retention, hold and lifecycle columns move exclusively through their owning
    transitions. A caller snapshot that differs in any of them is refused, so a
    stale snapshot handed to save() cannot revert state another writer
    committed since the snapshot was read.
    """
    repository = InMemoryArchiveDocumentRepository()
    metadata = _metadata("doc_immutability", "req-immutability")
    repository.save(metadata)

    now = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
    for field, value in {
        "purge_status": PurgeStatus.ELIGIBLE,
        "purge_eligible_at": now,
        "legal_hold_status": LegalHoldStatus.ACTIVE,
        "legal_hold_count": 2,
        "superseded_by_document_id": "doc_new",
    }.items():
        with pytest.raises(HistoricalIntegrityError) as excinfo:
            repository.save(metadata.model_copy(update={field: value}))
        assert field in str(excinfo.value)
    assert repository.get_by_document_id(metadata.document_id) == metadata

    touched = repository.save(metadata.model_copy(update={"updated_at": now}))
    assert touched.updated_at == now
    assert touched.model_copy(update={"updated_at": metadata.updated_at}) == metadata


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


def test_in_memory_lifecycle_transition_writes_only_the_decided_columns() -> None:
    """The transition touches the pointer columns and `updated_at`, nothing else.

    In particular the retention and hold columns of BOTH documents survive
    untouched, because the repository writes decided columns rather than the
    caller's snapshots (issue #166).
    """
    repository = InMemoryArchiveDocumentRepository()
    source = repository.save(_metadata("doc_1", "archive-request-1"))
    target = repository.save(_metadata("doc_2", "archive-request-2"))

    relationship, updated_source, updated_target = repository.apply_lifecycle_transition(
        source_document_id="doc_1",
        target_document_id="doc_2",
        transition_type=LifecycleTransitionType.SUPERSEDE,
        relationship=_relationship(),
    )

    assert relationship.lifecycle_relationship_id == "lifecycle_1"
    assert updated_source.superseded_by_document_id == "doc_2"
    assert updated_target.supersedes_document_id == "doc_1"
    unchanged = {
        field
        for field in type(source).model_fields
        if field not in {"superseded_by_document_id", "supersedes_document_id", "updated_at"}
    }
    for field in unchanged:
        assert getattr(updated_source, field) == getattr(source, field)
        assert getattr(updated_target, field) == getattr(target, field)
    listed = repository.list_lifecycle_relationships("doc_1")
    assert [item.lifecycle_relationship_id for item in listed] == ["lifecycle_1"]


def test_in_memory_lifecycle_transition_converges_on_an_exact_replay() -> None:
    """A replay whose pointers and relationship all agree returns the recorded
    relationship instead of conflicting - identical retries converge."""
    repository = InMemoryArchiveDocumentRepository()
    repository.save(_metadata("doc_1", "archive-request-1"))
    repository.save(_metadata("doc_2", "archive-request-2"))
    first, _, _ = repository.apply_lifecycle_transition(
        source_document_id="doc_1",
        target_document_id="doc_2",
        transition_type=LifecycleTransitionType.SUPERSEDE,
        relationship=_relationship(),
    )

    replayed, _, _ = repository.apply_lifecycle_transition(
        source_document_id="doc_1",
        target_document_id="doc_2",
        transition_type=LifecycleTransitionType.SUPERSEDE,
        relationship=_relationship("lifecycle_retry"),
    )

    assert replayed.lifecycle_relationship_id == first.lifecycle_relationship_id
    assert len(repository.list_lifecycle_relationships("doc_1")) == 1


def test_in_memory_lifecycle_transition_refused_by_stored_state_writes_nothing() -> None:
    """Validation runs against the STORED rows, and a refusal leaves no partial
    write: no pointer moved, no relationship recorded (issue #166)."""
    from app.archive.exceptions import UnsupportedLifecycleTransitionError

    repository = InMemoryArchiveDocumentRepository()
    source = repository.save(_metadata("doc_1", "archive-request-1"))
    repository.save(_metadata("doc_2", "archive-request-2"))
    purged = repository.begin_purge(
        document_id="doc_2", started_at=datetime(2026, 8, 29, tzinfo=timezone.utc)
    )
    assert purged is not None
    completed = repository.complete_purge(
        document_id="doc_2", purged_at=datetime(2026, 8, 29, 1, tzinfo=timezone.utc)
    )
    assert completed is not None

    with pytest.raises(UnsupportedLifecycleTransitionError):
        repository.apply_lifecycle_transition(
            source_document_id="doc_1",
            target_document_id="doc_2",
            transition_type=LifecycleTransitionType.SUPERSEDE,
            relationship=_relationship("lifecycle_refused"),
        )

    assert repository.get_by_document_id("doc_1") == source
    assert repository.get_by_document_id("doc_2") == completed
    assert repository.list_lifecycle_relationships("doc_1") == []


def test_in_memory_belts_refuse_destruction_under_a_drifted_summary() -> None:
    """Legacy drift: an active hold ROW under a CLEAR summary. Both destructive
    transitions must refuse on the row, and the refresh heals the summary."""
    from app.archive.models import LegalHoldRecord

    repository = InMemoryArchiveDocumentRepository()
    metadata = repository.save(_metadata("doc_drift", "archive-request-drift"))
    repository.save_legal_hold(
        LegalHoldRecord(
            legal_hold_id="hold_drift",
            document_id="doc_drift",
            hold_reason="litigation",
            authority_reference="REF-1",
            requested_by="actor_legal",
        )
    )
    assert metadata.legal_hold_status is LegalHoldStatus.CLEAR, "the drifted pair is in place"

    now = datetime(2026, 9, 13, tzinfo=timezone.utc)
    assert repository.begin_purge(document_id="doc_drift", started_at=now) is None
    assert repository.mark_purge_eligible(document_id="doc_drift", eligible_at=now) is None

    healed = repository.refresh_legal_hold_summary("doc_drift")
    assert healed is not None
    assert healed.legal_hold_status is LegalHoldStatus.ACTIVE
    assert healed.legal_hold_count == 1


def test_in_memory_release_refuses_unknown_and_foreign_holds() -> None:
    """A hold that does not exist for THIS document is the caller's refusal."""
    from app.archive.models import LegalHoldRecord

    repository = InMemoryArchiveDocumentRepository()
    repository.save(_metadata("doc_1", "archive-request-1"))
    repository.save(_metadata("doc_2", "archive-request-2"))
    repository.save_legal_hold(
        LegalHoldRecord(
            legal_hold_id="hold_other_doc",
            document_id="doc_2",
            hold_reason="litigation",
            authority_reference="REF-1",
            requested_by="actor_legal",
        )
    )
    released_at = datetime(2026, 9, 13, tzinfo=timezone.utc)

    assert (
        repository.release_and_record_legal_hold(
            document_id="doc_1",
            legal_hold_id="hold_absent",
            released_by="actor_legal",
            released_at=released_at,
            release_reason="not applicable",
        )
        is None
    )
    assert (
        repository.release_and_record_legal_hold(
            document_id="doc_1",
            legal_hold_id="hold_other_doc",
            released_by="actor_legal",
            released_at=released_at,
            release_reason="not applicable",
        )
        is None
    ), "a foreign document's hold must be indistinguishable from an absent one"
