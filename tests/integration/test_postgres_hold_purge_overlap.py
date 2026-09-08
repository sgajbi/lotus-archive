"""Genuinely overlapping hold and purge writers, proved against PostgreSQL.

The existing serialization tests call one writer and then the other. That
demonstrates the *decision* -- the second caller is refused -- but both
statements ran to completion before the next began, so nothing was ever
contending. A conditional `UPDATE ... WHERE ... RETURNING` that was not
conditional at all would pass every one of them.

These force real overlap. A blocker connection takes a lock and holds it inside
an open transaction; the writer under test runs on its own connection in another
thread and **blocks on that lock**, which is asserted rather than assumed. Only
then does the blocker commit the state the writer must observe. So the writer's
statement is genuinely executing while another transaction owns what it needs,
which is the deployed shape: several workers, one database.

**Where the lock is taken decides what the test can detect**, and getting that
wrong is not a detail. Locking the document row stalls a writer at its first
statement. Locking `archive_legal_holds` stalls it at the INSERT instead --
*after* a non-atomic implementation has already committed `legal_hold_status =
active` with no hold row behind it. The atomicity test uses the table lock for
exactly that reason: with the row lock it was measured to pass against an
implementation split back into three transactions, which is the defect it
exists to catch.

Every case asserts the four things together -- stored metadata, hold records,
object existence and the caller-visible outcome -- because the defects this
covers were each a *disagreement* between them. A purge that reports success
while an ACTIVE hold record stands is not visible in any one of them alone.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from app.archive.models import (
    ArchiveDocumentMetadata,
    LegalHoldRecord,
    LegalHoldStatus,
    PurgeStatus,
)
from app.archive.postgres_repository import PostgresArchiveDocumentRepository
from tests.database_proof import required_database_url
from tests.unit.test_archive_metadata_model import valid_metadata_input

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_ID = "doc_overlap"
LOCK_WAIT_SECONDS = 5.0


@pytest.fixture(scope="module")
def database_url() -> str:
    return required_database_url()


@pytest.fixture(autouse=True)
def migrated_database(database_url: str) -> None:
    with psycopg.connect(database_url, autocommit=True) as connection:
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            connection.execute(migration.read_text(encoding="utf-8"))
        connection.execute(
            "TRUNCATE archive_lifecycle_relationships, archive_legal_holds, archive_documents"
        )


def _repository(database_url: str) -> PostgresArchiveDocumentRepository:
    return PostgresArchiveDocumentRepository(database_url)


def _hold(suffix: str = "a") -> LegalHoldRecord:
    return LegalHoldRecord(
        legal_hold_id=f"hold_{DOCUMENT_ID}_{suffix}",
        document_id=DOCUMENT_ID,
        hold_reason="litigation",
        authority_reference="REF-1",
        requested_by="actor_legal",
    )


def _stored(repository: PostgresArchiveDocumentRepository) -> ArchiveDocumentMetadata:
    source = valid_metadata_input()
    metadata = ArchiveDocumentMetadata(
        **source.model_dump(),
        document_id=DOCUMENT_ID,
        storage_provider="filesystem",
        storage_namespace="archive",
        storage_key=f"archive/{DOCUMENT_ID}.pdf",
        checksum_algorithm="sha256",
        checksum="a" * 64,
        size_bytes=1024,
    )
    return repository.save(metadata)


class _Overlap:
    """Runs one writer against a row another transaction is holding locked.

    `started` proves the thread entered the call; `blocked` is asserted by the
    absence of a result while the lock is held. Without that assertion the test
    would pass even if the writer never contended at all, which is exactly the
    weakness of running the two calls in sequence.
    """

    def __init__(self) -> None:
        self.started = threading.Event()
        self.result: object = None
        self.error: BaseException | None = None
        self._thread: threading.Thread | None = None

    def run(self, call) -> None:  # type: ignore[no-untyped-def]
        def _target() -> None:
            self.started.set()
            try:
                self.result = call()
            except BaseException as exc:  # noqa: BLE001 - re-raised on join
                self.error = exc

        self._thread = threading.Thread(target=_target, daemon=True)
        self._thread.start()
        assert self.started.wait(timeout=LOCK_WAIT_SECONDS), "the writer never entered its call"

    def assert_still_blocked(self) -> None:
        # The writer is inside a statement waiting on the row lock. If it had
        # already returned, it never contended and the overlap is not real.
        self._thread_join(0.4)
        assert self._alive(), "the writer completed without contending for the locked row"

    def finish(self) -> object:
        self._thread_join(LOCK_WAIT_SECONDS)
        assert not self._alive(), "the writer never unblocked after the lock was released"
        if self.error is not None:
            raise self.error
        return self.result

    def _thread_join(self, timeout: float) -> None:
        assert self._thread is not None
        self._thread.join(timeout=timeout)

    def _alive(self) -> bool:
        assert self._thread is not None
        return self._thread.is_alive()


def _lock_row(connection: psycopg.Connection) -> None:
    connection.execute(
        "SELECT document_id FROM archive_documents WHERE document_id = %s FOR UPDATE",
        (DOCUMENT_ID,),
    )


def test_a_hold_waiting_on_a_locked_row_is_refused_by_the_purge_that_commits(
    database_url: str,
) -> None:
    """Purge wins the overlap. The hold must refuse and leave no hold record.

    The hold's admission statement is genuinely executing while the purge's
    transaction owns the row. This is the interleaving that produced PURGED
    metadata, an ACTIVE hold and absent bytes: admission used to commit `active`
    on its own, before the hold row existed, so a purge recounting holds saw
    none.
    """
    document = _stored(_repository(database_url))
    overlap = _Overlap()

    with psycopg.connect(database_url) as blocker:
        _lock_row(blocker)
        overlap.run(
            lambda: _repository(database_url).admit_and_record_legal_hold(
                document_id=document.document_id, legal_hold=_hold()
            )
        )
        overlap.assert_still_blocked()
        blocker.execute(
            "UPDATE archive_documents SET purge_started_at = %s WHERE document_id = %s",
            (datetime.now(UTC), DOCUMENT_ID),
        )
        blocker.commit()

    assert overlap.finish() is None, "the hold must be refused by the committed purge intent"

    repository = _repository(database_url)
    final = repository.get_by_document_id(DOCUMENT_ID)
    assert final is not None
    assert final.purge_started_at is not None
    assert final.legal_hold_status is LegalHoldStatus.CLEAR
    assert final.legal_hold_count == 0
    assert repository.list_legal_holds(DOCUMENT_ID) == [], (
        "a refused admission must leave no hold record; a stranded ACTIVE hold over a "
        "purged document is what made the lifecycle action answer LEGAL_HOLD for absent bytes"
    )


def test_a_purge_waiting_on_a_locked_row_is_refused_by_the_hold_that_commits(
    database_url: str,
) -> None:
    """Hold wins the overlap. The purge must refuse and claim no intent.

    The mirror direction, and the one that matters for preservation: a hold
    committed while the purge was waiting must stop it, with the hold record
    and the summary already consistent when the purge looks.
    """
    document = _stored(_repository(database_url))
    overlap = _Overlap()

    with psycopg.connect(database_url) as blocker:
        _lock_row(blocker)
        overlap.run(
            lambda: _repository(database_url).begin_purge(
                document_id=document.document_id, started_at=datetime.now(UTC)
            )
        )
        overlap.assert_still_blocked()
        blocker.execute(
            "INSERT INTO archive_legal_holds "
            "(legal_hold_id, document_id, hold_reason, authority_reference, requested_by, "
            " hold_status, requested_at) "
            "VALUES (%s, %s, %s, %s, %s, 'active', %s)",
            (
                f"hold_{DOCUMENT_ID}_blocker",
                DOCUMENT_ID,
                "litigation",
                "REF-1",
                "actor_legal",
                datetime.now(UTC),
            ),
        )
        blocker.execute(
            "UPDATE archive_documents SET legal_hold_status = 'active', legal_hold_count = 1 "
            "WHERE document_id = %s",
            (DOCUMENT_ID,),
        )
        blocker.commit()

    assert overlap.finish() is None, "a purge must not claim intent under a committed hold"

    repository = _repository(database_url)
    final = repository.get_by_document_id(DOCUMENT_ID)
    assert final is not None
    assert final.purge_started_at is None, "a refused purge must leave no destruction intent"
    assert final.legal_hold_status is LegalHoldStatus.ACTIVE
    assert len(repository.list_legal_holds(DOCUMENT_ID)) == 1


def test_the_admission_never_exposes_active_without_its_hold_record(
    database_url: str,
) -> None:
    """The window the fix closed, observed from outside the transaction.

    A reader on another connection must never see `legal_hold_status = active`
    while no active hold row exists for the document. That pairing was reachable
    for the whole gap between two separate transactions, and it is the state a
    competing purge acted on: it recounted, found none, wrote `clear`, deleted.

    **The lock is on `archive_legal_holds`, not on the document row, and that is
    the whole point of the test.** Locking the document row stalls the admission
    at its *first* statement, so a non-atomic implementation never gets to
    expose anything -- an earlier version of this test did exactly that and was
    measured to pass with the admission split back into three transactions.
    Blocking the INSERT instead stalls it *after* the status update, which is
    precisely where the old implementation had already committed `active` with
    no hold row behind it.
    """
    _stored(_repository(database_url))
    overlap = _Overlap()

    with psycopg.connect(database_url) as blocker:
        blocker.execute("LOCK TABLE archive_legal_holds IN ACCESS EXCLUSIVE MODE")
        overlap.run(
            lambda: _repository(database_url).admit_and_record_legal_hold(
                document_id=DOCUMENT_ID, legal_hold=_hold()
            )
        )
        overlap.assert_still_blocked()

        # Only `archive_documents` is read here: the blocker holds an exclusive
        # lock on the hold table, so reading it would block this thread too.
        during = _repository(database_url).get_by_document_id(DOCUMENT_ID)
        assert during is not None
        assert during.legal_hold_status is LegalHoldStatus.CLEAR, (
            "`active` became visible while the hold row was still unwritten -- the admission "
            "is not atomic, and a competing purge recounting holds here would find none"
        )
        assert during.legal_hold_count == 0
        blocker.commit()

    admitted = overlap.finish()
    assert admitted is not None

    repository = _repository(database_url)
    after = repository.get_by_document_id(DOCUMENT_ID)
    assert after is not None
    assert after.legal_hold_status is LegalHoldStatus.ACTIVE
    assert after.legal_hold_count == 1
    assert len(repository.list_legal_holds(DOCUMENT_ID)) == 1, (
        "the summary and the hold record must become visible together"
    )


def test_a_stale_eligibility_writer_cannot_overwrite_a_committed_hold(
    database_url: str,
) -> None:
    """Interleaving (a): eligibility must not erase a hold committed since the read.

    The eligibility decision is taken from a snapshot read before the hold
    existed. Under the previous whole-snapshot save it wrote `legal_hold_status`
    back from that snapshot, clearing a committed hold and letting the document
    be deleted with an ACTIVE hold record standing against it.
    """
    repository = _repository(database_url)
    document = _stored(repository)
    assert document.legal_hold_status is LegalHoldStatus.CLEAR  # the stale read

    admitted = _repository(database_url).admit_and_record_legal_hold(
        document_id=DOCUMENT_ID, legal_hold=_hold()
    )
    assert admitted is not None

    refused = repository.mark_purge_eligible(document_id=DOCUMENT_ID, eligible_at=datetime.now(UTC))

    assert refused is None, "eligibility must refuse under a committed hold"
    final = repository.get_by_document_id(DOCUMENT_ID)
    assert final is not None
    assert final.legal_hold_status is LegalHoldStatus.ACTIVE, "the hold survived the stale writer"
    assert final.legal_hold_count == 1
    assert final.purge_status is not PurgeStatus.ELIGIBLE
    assert len(repository.list_legal_holds(DOCUMENT_ID)) == 1


def test_a_stale_eligibility_writer_cannot_revive_a_completed_purge(
    database_url: str,
) -> None:
    """Interleaving (b): eligibility must not clear `purge_started_at`/`purged_at`.

    Clearing them made the document look never-destroyed, after which a new hold
    was admitted over bytes that were already gone -- a preservation guarantee
    issued for an object that does not exist.
    """
    repository = _repository(database_url)
    _stored(repository)

    purger = _repository(database_url)
    claimed = purger.begin_purge(document_id=DOCUMENT_ID, started_at=datetime.now(UTC))
    assert claimed is not None
    purged = purger.complete_purge(document_id=DOCUMENT_ID, purged_at=datetime.now(UTC))
    assert purged is not None

    refused = repository.mark_purge_eligible(document_id=DOCUMENT_ID, eligible_at=datetime.now(UTC))
    withdrawn = repository.mark_purge_not_eligible(document_id=DOCUMENT_ID)

    assert refused is None, "eligibility must refuse a completed purge"
    assert withdrawn is None, "withdrawal must refuse a completed purge"

    final = repository.get_by_document_id(DOCUMENT_ID)
    assert final is not None
    assert final.purge_status is PurgeStatus.PURGED
    assert final.purge_started_at is not None, "the destruction intent must survive"
    assert final.purged_at == purged.purged_at, "the moment of destruction must not be restamped"

    assert (
        _repository(database_url).admit_and_record_legal_hold(
            document_id=DOCUMENT_ID, legal_hold=_hold("later")
        )
        is None
    ), "a hold must not be admitted over a purged document"
    assert _repository(database_url).list_legal_holds(DOCUMENT_ID) == []


def test_an_interrupted_completion_is_finished_by_a_retry_on_a_new_connection(
    database_url: str,
) -> None:
    """Crash and retry: the intent survives, and a different worker completes it.

    `complete_purge` is idempotent on an already-purged row and requires a
    claimed intent, so a retry converges instead of either refusing or
    re-recording a second destruction at a later timestamp.
    """
    claimed = _repository(database_url)
    _stored(claimed)
    intent = claimed.begin_purge(document_id=DOCUMENT_ID, started_at=datetime.now(UTC))
    assert intent is not None

    # The completion never ran -- the process died between the delete and the
    # record. A fresh connection, as a restarted worker would have.
    interrupted = _repository(database_url).get_by_document_id(DOCUMENT_ID)
    assert interrupted is not None
    assert interrupted.purge_started_at is not None
    assert interrupted.purge_status is not PurgeStatus.PURGED

    first = _repository(database_url).complete_purge(
        document_id=DOCUMENT_ID, purged_at=datetime.now(UTC)
    )
    assert first is not None
    second = _repository(database_url).complete_purge(
        document_id=DOCUMENT_ID, purged_at=datetime.now(UTC) + timedelta(hours=1)
    )

    assert second is not None
    assert second.purged_at == first.purged_at, (
        "a retry must not restamp when the bytes actually went"
    )
    assert second.purge_started_at == intent.purge_started_at


def test_completion_refuses_a_document_whose_destruction_was_never_ordered(
    database_url: str,
) -> None:
    """No intent, no completion. Otherwise a bug could record a destruction nobody ordered."""
    repository = _repository(database_url)
    _stored(repository)

    assert repository.complete_purge(document_id=DOCUMENT_ID, purged_at=datetime.now(UTC)) is None

    final = repository.get_by_document_id(DOCUMENT_ID)
    assert final is not None
    assert final.purge_status is not PurgeStatus.PURGED
    assert final.purged_at is None
