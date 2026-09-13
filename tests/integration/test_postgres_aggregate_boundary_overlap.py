"""C6-ARC-01 (issue #166): the aggregate write boundary under genuine overlap.

Two residual stale-write paths survived the C5 fixes, and each is forced here
with a blocker transaction holding exactly the lock the shipped writer must
serialize on:

* A summary refresh (and the release path that ends in one) used to recount
  holds in one transaction and write the result in another. Blocked behind an
  in-flight admission, the old shape counted BEFORE the new hold committed and
  wrote its stale CLEAR/0 AFTER - the precise column `begin_purge` trusts. The
  repository now locks the document row first and derives the count in the
  same transaction, so a refresh that unblocks sees the admission it waited on.

* A lifecycle transition used to write both documents back as whole snapshots.
  Blocked behind a purge or a hold admission, the old shape validated clean
  pre-race reads and then overwrote the raced writer's committed purge or hold
  columns. The repository now locks both rows in sorted id order, re-validates
  the STORED rows, and writes only the columns the transition decides.

The blocker's writes are the same statements the shipped writers run, executed
raw inside one open transaction so the overlap window can be held deliberately.
Every case asserts the stored metadata, the hold/relationship rows and the
follow-on destruction decision together, because each defect was a
disagreement between them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from app.archive.exceptions import (
    SupersessionConflictError,
    UnsupportedLifecycleTransitionError,
)
from app.archive.models import (
    ArchiveDocumentMetadata,
    LegalHoldRecord,
    LegalHoldStatus,
    LifecycleRelationshipRecord,
    LifecycleTransitionType,
    PurgeStatus,
)
from app.archive.postgres_repository import PostgresArchiveDocumentRepository
from tests.database_proof import required_database_url
from tests.integration.test_postgres_hold_purge_overlap import _Overlap
from tests.unit.test_archive_metadata_model import valid_metadata_input

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = required_database_url()
RECONCILE_MIGRATION = ROOT / "migrations" / "013_reconcile_drifted_legal_hold_summaries.sql"


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


def _stored(
    repository: PostgresArchiveDocumentRepository, document_id: str
) -> ArchiveDocumentMetadata:
    source = valid_metadata_input(archive_request_id=f"req-{document_id}")
    metadata = ArchiveDocumentMetadata(
        **source.model_dump(),
        document_id=document_id,
        storage_provider="filesystem",
        storage_namespace="archive",
        storage_key=f"archive/{document_id}.pdf",
        checksum_algorithm="sha256",
        checksum="a" * 64,
        size_bytes=1024,
    )
    return repository.save(metadata)


def _hold(document_id: str, suffix: str) -> LegalHoldRecord:
    return LegalHoldRecord(
        legal_hold_id=f"hold_{document_id}_{suffix}",
        document_id=document_id,
        hold_reason="litigation",
        authority_reference="REF-1",
        requested_by="actor_legal",
    )


def _relationship(
    relationship_id: str, source_document_id: str, target_document_id: str
) -> LifecycleRelationshipRecord:
    return LifecycleRelationshipRecord(
        lifecycle_relationship_id=relationship_id,
        source_document_id=source_document_id,
        target_document_id=target_document_id,
        transition_type=LifecycleTransitionType.SUPERSEDE,
        transition_reason="Approved replacement",
        transition_reason_code="archive_document_supersession_requested",
        requested_by="operations-user",
    )


def _begin_admission(connection: psycopg.Connection, document_id: str, hold_id: str) -> None:
    """The shipped admission's statements, raw, left UNCOMMITTED.

    Statement-for-statement what `admit_and_record_legal_hold` runs, so the
    blocker holds exactly the document-row lock a real concurrent admission
    would hold for the duration of its transaction.
    """
    now = datetime.now(UTC)
    connection.execute(
        "UPDATE archive_documents SET legal_hold_status = 'active', updated_at = %s "
        "WHERE document_id = %s AND purge_started_at IS NULL",
        (now, document_id),
    )
    connection.execute(
        "INSERT INTO archive_legal_holds "
        "(legal_hold_id, document_id, hold_reason, authority_reference, requested_by, "
        " hold_status, requested_at) "
        "VALUES (%s, %s, %s, %s, %s, 'active', %s)",
        (hold_id, document_id, "litigation", "REF-1", "actor_legal", now),
    )
    connection.execute(
        "UPDATE archive_documents SET legal_hold_count = ("
        "    SELECT count(*) FROM archive_legal_holds"
        "    WHERE document_id = %s AND hold_status = 'active'"
        "), updated_at = %s WHERE document_id = %s",
        (document_id, now, document_id),
    )


def _active_hold_rows(document_id: str) -> list[str]:
    with psycopg.connect(DATABASE_URL) as connection:
        rows = connection.execute(
            "SELECT legal_hold_id FROM archive_legal_holds "
            "WHERE document_id = %s AND hold_status = 'active' ORDER BY legal_hold_id",
            (document_id,),
        ).fetchall()
    return [row[0] for row in rows]


def test_a_refresh_blocked_by_an_admission_counts_the_hold_it_waited_on() -> None:
    """C6-ARC-01A, the read-refresh half.

    Hold A is released; a refresh runs while an admission of hold B holds the
    document row uncommitted. The OLD shape counted holds before blocking (A
    released, B invisible -> zero) and wrote CLEAR/0 after the admission
    committed, so the purge guard column said clear while an ACTIVE hold row
    stood. The refresh must instead serialize FIRST and count the hold whose
    commit it waited on.
    """
    document_id = "doc_refresh_race"
    repository = _repository()
    _stored(repository, document_id)
    admitted = repository.admit_and_record_legal_hold(
        document_id=document_id, legal_hold=_hold(document_id, "a")
    )
    assert admitted is not None
    released = repository.release_and_record_legal_hold(
        document_id=document_id,
        legal_hold_id=f"hold_{document_id}_a",
        released_by="actor_legal",
        released_at=datetime.now(UTC),
        release_reason="matter closed",
    )
    assert released is not None
    assert released[1].legal_hold_status is LegalHoldStatus.CLEAR

    overlap = _Overlap()
    with psycopg.connect(DATABASE_URL) as blocker:
        _begin_admission(blocker, document_id, f"hold_{document_id}_b")
        overlap.run(lambda: _repository().refresh_legal_hold_summary(document_id))
        overlap.assert_still_blocked()
        blocker.commit()

    refreshed = overlap.finish()
    assert isinstance(refreshed, ArchiveDocumentMetadata)
    assert refreshed.legal_hold_status is LegalHoldStatus.ACTIVE, (
        "the refresh unblocked after the admission committed, so its recount must "
        "include the admitted hold - a CLEAR here is the stale recount that re-arms purge"
    )
    assert refreshed.legal_hold_count == 1

    assert (
        _repository().begin_purge(document_id=document_id, started_at=datetime.now(UTC)) is None
    ), "destruction must stay refused while the admitted hold stands"
    assert (
        _repository().mark_purge_eligible(document_id=document_id, eligible_at=datetime.now(UTC))
        is None
    )
    final = _repository().get_by_document_id(document_id)
    assert final is not None
    assert final.legal_hold_status is LegalHoldStatus.ACTIVE
    assert final.legal_hold_count == 1
    assert final.purge_started_at is None
    assert _active_hold_rows(document_id) == [f"hold_{document_id}_b"]


def test_a_release_blocked_by_an_admission_keeps_the_new_hold_counted() -> None:
    """C6-ARC-01A, the release half.

    Hold A is being released while an admission of hold B holds the document
    row uncommitted. The OLD shape cleared A's row immediately (no document
    lock), recounted before B committed, and wrote CLEAR/0 over B's summary
    afterwards. The release must instead serialize on the document row first:
    when it proceeds, A is clear, B is counted, and destruction stays refused.
    """
    document_id = "doc_release_race"
    repository = _repository()
    _stored(repository, document_id)
    admitted = repository.admit_and_record_legal_hold(
        document_id=document_id, legal_hold=_hold(document_id, "a")
    )
    assert admitted is not None

    overlap = _Overlap()
    with psycopg.connect(DATABASE_URL) as blocker:
        _begin_admission(blocker, document_id, f"hold_{document_id}_b")
        overlap.run(
            lambda: _repository().release_and_record_legal_hold(
                document_id=document_id,
                legal_hold_id=f"hold_{document_id}_a",
                released_by="actor_legal",
                released_at=datetime.now(UTC),
                release_reason="matter closed",
            )
        )
        overlap.assert_still_blocked()
        blocker.commit()

    result = overlap.finish()
    assert isinstance(result, tuple)
    released_hold, metadata = result
    assert released_hold.hold_status is LegalHoldStatus.CLEAR
    assert released_hold.release_reason == "matter closed"
    assert metadata.legal_hold_status is LegalHoldStatus.ACTIVE, (
        "releasing A must not clear the summary while B stands"
    )
    assert metadata.legal_hold_count == 1

    assert _repository().begin_purge(document_id=document_id, started_at=datetime.now(UTC)) is None
    assert _active_hold_rows(document_id) == [f"hold_{document_id}_b"]


def test_a_lifecycle_transition_blocked_by_a_purge_refuses_on_the_stored_rows() -> None:
    """C6-ARC-01B, the refusal direction.

    The transition validated clean pre-race reads; a purge of the target
    commits while the transition waits on the row lock. The OLD shape then
    wrote the stale snapshots whole, reverting PURGED + intent + purged_at to
    NOT_ELIGIBLE + null + null. The transition must instead re-validate the
    stored rows it locked and refuse, leaving the purge record untouched.
    """
    source_id, target_id = "doc_life_a", "doc_life_b"
    repository = _repository()
    _stored(repository, source_id)
    _stored(repository, target_id)

    overlap = _Overlap()
    with psycopg.connect(DATABASE_URL) as blocker:
        now = datetime.now(UTC)
        blocker.execute(
            "UPDATE archive_documents SET purge_started_at = %s WHERE document_id = %s",
            (now, target_id),
        )
        blocker.execute(
            "UPDATE archive_documents SET purge_status = 'purged', purged_at = %s "
            "WHERE document_id = %s",
            (now, target_id),
        )
        overlap.run(
            lambda: _repository().apply_lifecycle_transition(
                source_document_id=source_id,
                target_document_id=target_id,
                transition_type=LifecycleTransitionType.SUPERSEDE,
                relationship=_relationship("life_purge_race", source_id, target_id),
            )
        )
        overlap.assert_still_blocked()
        blocker.commit()

    with pytest.raises(UnsupportedLifecycleTransitionError):
        overlap.finish()

    target = _repository().get_by_document_id(target_id)
    assert target is not None
    assert target.purge_status is PurgeStatus.PURGED, "the committed purge must survive"
    assert target.purge_started_at is not None, "the destruction intent must not be erased"
    assert target.purged_at is not None, "the moment of destruction must not be erased"
    source = _repository().get_by_document_id(source_id)
    assert source is not None
    assert source.superseded_by_document_id is None, "a refused transition writes nothing"
    assert _repository().list_lifecycle_relationships(source_id) == []


def test_a_lifecycle_transition_blocked_by_a_hold_applies_without_erasing_it() -> None:
    """C6-ARC-01B, the column-scope direction.

    A hold on the target commits while the transition waits. A hold does not
    forbid supersession, so the transition must APPLY - and must not carry its
    stale snapshot's CLEAR/0 over the committed hold summary, which is what the
    whole-row save did and what re-armed destruction against an ACTIVE hold.
    """
    source_id, target_id = "doc_hold_a", "doc_hold_b"
    repository = _repository()
    _stored(repository, source_id)
    _stored(repository, target_id)

    overlap = _Overlap()
    with psycopg.connect(DATABASE_URL) as blocker:
        _begin_admission(blocker, target_id, f"hold_{target_id}_h")
        overlap.run(
            lambda: _repository().apply_lifecycle_transition(
                source_document_id=source_id,
                target_document_id=target_id,
                transition_type=LifecycleTransitionType.SUPERSEDE,
                relationship=_relationship("life_hold_race", source_id, target_id),
            )
        )
        overlap.assert_still_blocked()
        blocker.commit()

    result = overlap.finish()
    assert isinstance(result, tuple)
    relationship, source_after, target_after = result
    assert relationship.lifecycle_relationship_id == "life_hold_race"
    assert source_after.superseded_by_document_id == target_id
    assert target_after.supersedes_document_id == source_id
    assert target_after.legal_hold_status is LegalHoldStatus.ACTIVE, (
        "the transition must not erase the hold summary committed while it waited"
    )
    assert target_after.legal_hold_count == 1

    assert _repository().begin_purge(document_id=target_id, started_at=datetime.now(UTC)) is None
    assert _active_hold_rows(target_id) == [f"hold_{target_id}_h"]
    assert [
        item.lifecycle_relationship_id
        for item in _repository().list_lifecycle_relationships(source_id)
    ] == ["life_hold_race"]


def test_lifecycle_replay_converges_and_a_second_transition_conflicts() -> None:
    """Identical retries converge on the recorded relationship - across
    connections, as a restarted worker would retry - and a DIFFERENT transition
    from the now-historical source is a typed conflict."""
    source_id, target_id, other_id = "doc_replay_a", "doc_replay_b", "doc_replay_c"
    repository = _repository()
    _stored(repository, source_id)
    _stored(repository, target_id)
    _stored(repository, other_id)

    first, _, _ = repository.apply_lifecycle_transition(
        source_document_id=source_id,
        target_document_id=target_id,
        transition_type=LifecycleTransitionType.SUPERSEDE,
        relationship=_relationship("life_first", source_id, target_id),
    )

    replayed, source_after, target_after = _repository().apply_lifecycle_transition(
        source_document_id=source_id,
        target_document_id=target_id,
        transition_type=LifecycleTransitionType.SUPERSEDE,
        relationship=_relationship("life_retry", source_id, target_id),
    )

    assert replayed.lifecycle_relationship_id == first.lifecycle_relationship_id
    assert source_after.superseded_by_document_id == target_id
    assert target_after.supersedes_document_id == source_id
    assert [
        item.lifecycle_relationship_id
        for item in _repository().list_lifecycle_relationships(source_id)
    ] == ["life_first"]

    with pytest.raises(SupersessionConflictError):
        _repository().apply_lifecycle_transition(
            source_document_id=source_id,
            target_document_id=other_id,
            transition_type=LifecycleTransitionType.SUPERSEDE,
            relationship=_relationship("life_conflict", source_id, other_id),
        )

    # Restart: a fresh connection reads the durable pointers, not a cache.
    after_restart = _repository().get_by_document_id(source_id)
    assert after_restart is not None
    assert after_restart.superseded_by_document_id == target_id


def test_a_legacy_drifted_summary_is_refused_by_the_belt_and_healed_by_the_migration() -> None:
    """Legacy drift: an active hold ROW under a CLEAR summary, as the historic
    race left retained rows. The hold-row belts must refuse destruction while
    the drift stands, and migration 013 must heal it idempotently."""
    document_id = "doc_drift"
    repository = _repository()
    _stored(repository, document_id)
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO archive_legal_holds "
            "(legal_hold_id, document_id, hold_reason, authority_reference, requested_by, "
            " hold_status, requested_at) "
            "VALUES (%s, %s, %s, %s, %s, 'active', %s)",
            (
                f"hold_{document_id}_legacy",
                document_id,
                "litigation",
                "REF-1",
                "actor_legal",
                datetime.now(UTC),
            ),
        )
    drifted = repository.get_by_document_id(document_id)
    assert drifted is not None
    assert drifted.legal_hold_status is LegalHoldStatus.CLEAR, "the drifted pair is in place"

    assert repository.begin_purge(document_id=document_id, started_at=datetime.now(UTC)) is None, (
        "the hold-row belt must refuse destruction even under a drifted CLEAR summary"
    )
    assert (
        repository.mark_purge_eligible(document_id=document_id, eligible_at=datetime.now(UTC))
        is None
    )

    reconcile_sql = RECONCILE_MIGRATION.read_text(encoding="utf-8")
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(reconcile_sql)
    healed = repository.get_by_document_id(document_id)
    assert healed is not None
    assert healed.legal_hold_status is LegalHoldStatus.ACTIVE
    assert healed.legal_hold_count == 1

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(reconcile_sql)
    second = repository.get_by_document_id(document_id)
    assert second is not None
    assert second.updated_at == healed.updated_at, (
        "a re-run with no drift must update nothing - the repair is idempotent"
    )


def test_a_legacy_half_erased_chain_conflicts_as_a_typed_refusal() -> None:
    """Legacy drift on the lifecycle side: the old whole-row save could clear
    `superseded_by_document_id` while the relationship row survived. A new
    transition from that source passes the stored-row validation and is caught
    by the one-successor unique index - which must surface as the typed
    supersession conflict, not a raw driver error, and must write nothing."""
    source_id, target_id, other_id = "doc_chain_a", "doc_chain_b", "doc_chain_c"
    repository = _repository()
    _stored(repository, source_id)
    _stored(repository, target_id)
    _stored(repository, other_id)
    repository.apply_lifecycle_transition(
        source_document_id=source_id,
        target_document_id=target_id,
        transition_type=LifecycleTransitionType.SUPERSEDE,
        relationship=_relationship("life_chain", source_id, target_id),
    )
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "UPDATE archive_documents SET superseded_by_document_id = NULL WHERE document_id = %s",
            (source_id,),
        )

    with pytest.raises(SupersessionConflictError):
        _repository().apply_lifecycle_transition(
            source_document_id=source_id,
            target_document_id=other_id,
            transition_type=LifecycleTransitionType.SUPERSEDE,
            relationship=_relationship("life_chain_second", source_id, other_id),
        )

    other = _repository().get_by_document_id(other_id)
    assert other is not None
    assert other.supersedes_document_id is None, "the refused transition rolled back whole"
    assert [
        item.lifecycle_relationship_id
        for item in _repository().list_lifecycle_relationships(source_id)
    ] == ["life_chain"]


def test_the_migration_repair_blocked_by_an_admission_does_not_overwrite_its_hold() -> None:
    """Issue #170: the standalone repair must serialize BEFORE deriving its snapshot.

    Reverse legacy drift is seeded - summary ACTIVE/1 with no hold rows - and a
    hold admission holds the document row uncommitted when migration 013 runs
    through its actual entry point (the file text on its own connection, the
    way every environment applies it). An unserialized repair derives CLEAR/0
    for the document - the admission is invisible to its statement snapshot -
    blocks on the admission's lock, and under READ COMMITTED writes that stale
    CLEAR/0 after the admission commits: only the WHERE clause is re-evaluated
    against the new row version, never the FROM-derived table. That is the
    repair itself recreating the drift it exists to heal, on the exact summary
    column reads and signed posture trust.

    The healed end state must agree with the committed ACTIVE hold row, purge
    fields must stay untouched, and an unchanged rerun must remain idempotent.
    """
    document_id = "doc_migration_race"
    repository = _repository()
    _stored(repository, document_id)
    # The reverse drift shape, seeded past the guards: a summary asserting a
    # hold that has no row behind it, as the historic stale recount left rows.
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(
            "UPDATE archive_documents SET legal_hold_status = 'active', legal_hold_count = 1 "
            "WHERE document_id = %s",
            (document_id,),
        )
    reconcile_sql = RECONCILE_MIGRATION.read_text(encoding="utf-8")

    def run_repair() -> None:
        # Fixture-style application: one autocommit connection, the whole file.
        with psycopg.connect(DATABASE_URL, autocommit=True) as migrator:
            migrator.execute(reconcile_sql)

    overlap = _Overlap()
    with psycopg.connect(DATABASE_URL) as blocker:
        _begin_admission(blocker, document_id, f"hold_{document_id}_b")
        overlap.run(run_repair)
        overlap.assert_still_blocked()
        blocker.commit()
    overlap.finish()

    healed = repository.get_by_document_id(document_id)
    assert healed is not None
    assert healed.legal_hold_status is LegalHoldStatus.ACTIVE, (
        "the repair unblocked after the admission committed, so its derivation must include "
        "the admitted hold - a CLEAR here is the repair writing its pre-admission snapshot"
    )
    assert healed.legal_hold_count == 1
    assert _active_hold_rows(document_id) == [f"hold_{document_id}_b"]
    assert healed.purge_status is PurgeStatus.NOT_ELIGIBLE, "the repair never touches purge fields"
    assert healed.purge_started_at is None
    assert healed.purged_at is None

    # An unchanged rerun through the same entry point stays idempotent.
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(reconcile_sql)
    second = repository.get_by_document_id(document_id)
    assert second is not None
    assert second.updated_at == healed.updated_at, "a no-drift rerun must update nothing"
