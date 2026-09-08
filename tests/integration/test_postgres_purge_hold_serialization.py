"""C5-ARC-01 proven against PostgreSQL, not the in-memory double.

The in-memory repository has no conditional-update semantics: its `begin_purge`
and `admit_and_record_legal_hold` are single-threaded Python that cannot demonstrate mutual
exclusion between concurrent writers. It shows the *decision*; only the database
shows the *serialization*.

These tests use two independent connections through the real
`PostgresArchiveDocumentRepository`, so the exclusion is decided by
`UPDATE ... WHERE ... RETURNING` against one row, which is what runs in a
deployment with several workers or replicas.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from tests.database_proof import required_database_url
from app.archive.models import (
    ArchiveDocumentMetadata,
    LegalHoldRecord,
    LegalHoldStatus,
    PurgeStatus,
)
from app.archive.postgres_repository import PostgresArchiveDocumentRepository
from tests.unit.test_archive_metadata_model import valid_metadata_input

ROOT = Path(__file__).resolve().parents[2]
# Resolved through the shared helper so an unreachable database FAILS the lane
# that requires the proof instead of skipping it. These tests skipped in every
# run for their whole existence before CI provided a database; a skip reported
# as a pass is the same shape as a gate that cannot fail.
DATABASE_URL = required_database_url()


@pytest.fixture(autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            connection.execute(migration.read_text(encoding="utf-8"))
        connection.execute(
            "TRUNCATE archive_lifecycle_relationships, archive_legal_holds, archive_documents"
        )


def _repository() -> PostgresArchiveDocumentRepository:
    return PostgresArchiveDocumentRepository(DATABASE_URL)


def _hold(document_id: str, *, suffix: str = "a") -> LegalHoldRecord:
    return LegalHoldRecord(
        legal_hold_id=f"hold_{document_id}_{suffix}",
        document_id=document_id,
        hold_reason="litigation",
        authority_reference="REF-1",
        requested_by="actor_legal",
    )


def _stored(repository: PostgresArchiveDocumentRepository) -> ArchiveDocumentMetadata:
    source = valid_metadata_input()
    metadata = ArchiveDocumentMetadata(
        **source.model_dump(),
        document_id="doc_c5arc01",
        storage_provider="filesystem",
        storage_namespace="archive",
        storage_key="archive/doc_c5arc01.pdf",
        checksum_algorithm="sha256",
        checksum="a" * 64,
        size_bytes=1024,
    )
    return repository.save(metadata)


def test_only_one_of_two_concurrent_writers_claims_the_document() -> None:
    """The exclusion itself, decided by the database rather than by either caller.

    Two independent repository instances — separate connections — race for the
    same row. Exactly one must win, and the loser must observe the winner's
    committed state rather than proceeding on its own read.
    """
    writer_a = _repository()
    writer_b = _repository()
    document = _stored(writer_a)

    purge_claim = writer_a.begin_purge(
        document_id=document.document_id, started_at=datetime.now(UTC)
    )
    hold_claim = writer_b.admit_and_record_legal_hold(
        document_id=document.document_id, legal_hold=_hold(document.document_id)
    )

    assert purge_claim is not None, "the first writer must acquire the intent"
    assert hold_claim is None, "the second writer must be refused by the row, not by its own read"

    final = writer_b.get_by_document_id(document.document_id)
    assert final is not None
    assert final.purge_started_at is not None
    assert final.legal_hold_status is LegalHoldStatus.CLEAR


def test_a_hold_admitted_first_refuses_a_concurrent_purge() -> None:
    """The mirror direction, same row, same mechanism."""
    writer_a = _repository()
    writer_b = _repository()
    document = _stored(writer_a)

    hold_claim = writer_a.admit_and_record_legal_hold(
        document_id=document.document_id, legal_hold=_hold(document.document_id)
    )
    purge_claim = writer_b.begin_purge(
        document_id=document.document_id, started_at=datetime.now(UTC)
    )

    assert hold_claim is not None
    assert purge_claim is None, "a purge must not acquire intent under an active hold"

    final = writer_a.get_by_document_id(document.document_id)
    assert final is not None
    assert final.purge_started_at is None, "a refused purge must leave no destruction intent"
    assert final.legal_hold_status is LegalHoldStatus.ACTIVE


def test_reclaiming_an_existing_intent_is_idempotent_not_refused() -> None:
    """An interrupted purge must be completable by whichever worker retries it.

    Returning None here would strand a document whose object is already deleted:
    no retry could finish the record, and the row would keep asserting that the
    document is retained.
    """
    repository = _repository()
    document = _stored(repository)
    started = datetime.now(UTC)

    first = repository.begin_purge(document_id=document.document_id, started_at=started)
    second = repository.begin_purge(
        document_id=document.document_id, started_at=started + timedelta(minutes=5)
    )

    assert first is not None and second is not None
    assert second.purge_started_at == first.purge_started_at, (
        "a re-entrant claim must not move the recorded instant"
    )


def test_a_stale_writer_cannot_revert_committed_purge_state() -> None:
    """The column-scoped summary write, against a real row.

    A caller holding a pre-purge snapshot updates the hold counters after a
    purge has committed. The counters must move and the purge state must not,
    because the repository is given values rather than a document to serialise.
    """
    repository = _repository()
    document = _stored(repository)
    stale = repository.get_by_document_id(document.document_id)
    assert stale is not None and stale.purge_started_at is None

    claimed = repository.begin_purge(document_id=document.document_id, started_at=datetime.now(UTC))
    assert claimed is not None
    purged = repository.save(
        claimed.model_copy(
            update={"purge_status": PurgeStatus.PURGED, "purged_at": datetime.now(UTC)}
        )
    )

    repository.update_legal_hold_summary(
        document_id=document.document_id,
        legal_hold_status=LegalHoldStatus.ACTIVE,
        legal_hold_count=1,
    )

    final = repository.get_by_document_id(document.document_id)
    assert final is not None
    assert final.purge_status is PurgeStatus.PURGED
    assert final.purge_started_at == purged.purge_started_at
    assert final.purged_at == purged.purged_at
    assert final.legal_hold_status is LegalHoldStatus.ACTIVE
    assert final.legal_hold_count == 1


def test_the_committed_transition_survives_a_new_connection() -> None:
    """Restart: a fresh repository reads what the database holds, not a cache."""
    repository = _repository()
    document = _stored(repository)
    claimed = repository.begin_purge(document_id=document.document_id, started_at=datetime.now(UTC))
    assert claimed is not None

    after_restart = _repository().get_by_document_id(document.document_id)

    assert after_restart is not None
    assert after_restart.purge_started_at == claimed.purge_started_at
    assert (
        _repository().admit_and_record_legal_hold(
            document_id=document.document_id, legal_hold=_hold(document.document_id)
        )
        is None
    )


def test_the_claims_refuse_an_unknown_document() -> None:
    """The same refusal against the real database, where no row matches at all."""
    repository = _repository()

    assert repository.begin_purge(document_id="doc_absent", started_at=datetime.now(UTC)) is None
    assert (
        repository.admit_and_record_legal_hold(
            document_id="doc_absent", legal_hold=_hold("doc_absent")
        )
        is None
    )
    assert (
        repository.update_legal_hold_summary(
            document_id="doc_absent",
            legal_hold_status=LegalHoldStatus.ACTIVE,
            legal_hold_count=1,
        )
        is None
    )
