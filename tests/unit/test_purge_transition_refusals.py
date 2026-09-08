"""Every refusal a guarded purge transition can make, and what it answers instead.

The PostgreSQL suite proves these guards hold under genuinely concurrent
writers. These prove the *decision table* — which conditions refuse, and what
the service reports when one does — against the in-memory repository, where each
case can be constructed exactly rather than raced into existence.

Both layers are needed and neither substitutes for the other. A guard that is
correct in SQL and unreachable through the service protects nothing, and a
decision table that is right in Python says nothing about two workers.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.archive.exceptions import DocumentNotFoundError
from app.archive.models import (
    ArchiveDocumentMetadata,
    LegalHoldStatus,
    PurgeStatus,
)
from app.archive.purge_transitions import evaluate_purge, reclassify_refused_transition
from app.archive.repository import InMemoryArchiveDocumentRepository
from tests.unit.test_archive_metadata_model import valid_metadata_input

DOCUMENT_ID = "doc_guard"
TODAY = date(2026, 9, 8)


def _repository(**overrides: object) -> InMemoryArchiveDocumentRepository:
    repository = InMemoryArchiveDocumentRepository()
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
    repository.save(metadata.model_copy(update=dict(overrides)))
    return repository


def _stored(repository: InMemoryArchiveDocumentRepository) -> ArchiveDocumentMetadata:
    metadata = repository.get_by_document_id(DOCUMENT_ID)
    assert metadata is not None
    return metadata


# --------------------------------------------------------------- eligibility


def test_eligibility_refuses_an_unknown_document() -> None:
    repository = InMemoryArchiveDocumentRepository()

    assert (
        repository.mark_purge_eligible(document_id="doc_absent", eligible_at=datetime.now(UTC))
        is None
    )


def test_eligibility_refuses_a_started_purge() -> None:
    """Irreversible state outranks a retention decision taken from an older read."""
    repository = _repository(purge_started_at=datetime.now(UTC))

    assert (
        repository.mark_purge_eligible(document_id=DOCUMENT_ID, eligible_at=datetime.now(UTC))
        is None
    )


def test_eligibility_refuses_a_completed_purge() -> None:
    repository = _repository(
        purge_started_at=datetime.now(UTC),
        purged_at=datetime.now(UTC),
        purge_status=PurgeStatus.PURGED,
    )

    assert (
        repository.mark_purge_eligible(document_id=DOCUMENT_ID, eligible_at=datetime.now(UTC))
        is None
    )
    assert _stored(repository).purge_status is PurgeStatus.PURGED


def test_eligibility_refuses_an_active_hold() -> None:
    """The guard eligibility carries and withdrawal does not: it grants permission to destroy."""
    repository = _repository(legal_hold_status=LegalHoldStatus.ACTIVE, legal_hold_count=1)

    assert (
        repository.mark_purge_eligible(document_id=DOCUMENT_ID, eligible_at=datetime.now(UTC))
        is None
    )
    assert _stored(repository).purge_status is not PurgeStatus.ELIGIBLE


def test_eligibility_keeps_the_first_timestamp_rather_than_restamping() -> None:
    """A re-evaluation must not make an old decision look recent."""
    repository = _repository()
    first = repository.mark_purge_eligible(
        document_id=DOCUMENT_ID, eligible_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    assert first is not None

    again = repository.mark_purge_eligible(
        document_id=DOCUMENT_ID, eligible_at=datetime(2026, 6, 1, tzinfo=UTC)
    )

    assert again is not None
    assert again.purge_eligible_at == first.purge_eligible_at


# --------------------------------------------------------------- withdrawal


def test_withdrawal_refuses_an_unknown_document() -> None:
    repository = InMemoryArchiveDocumentRepository()

    assert repository.mark_purge_not_eligible(document_id="doc_absent") is None


def test_withdrawal_proceeds_under_an_active_hold() -> None:
    """The case a hold guard would wrongly refuse.

    Withdrawal is the transition taken *because* a hold is active. Carrying the
    eligibility guard here would refuse exactly the situation it exists for, and
    the document would keep reporting `eligible` while held.
    """
    repository = _repository(legal_hold_status=LegalHoldStatus.ACTIVE, legal_hold_count=1)

    withdrawn = repository.mark_purge_not_eligible(document_id=DOCUMENT_ID)

    assert withdrawn is not None
    assert withdrawn.purge_status is PurgeStatus.NOT_ELIGIBLE
    assert withdrawn.legal_hold_status is LegalHoldStatus.ACTIVE


def test_withdrawal_refuses_a_completed_purge() -> None:
    """Withdrawing eligibility from destroyed bytes would say destruction was never permitted."""
    repository = _repository(
        purge_started_at=datetime.now(UTC),
        purged_at=datetime.now(UTC),
        purge_status=PurgeStatus.PURGED,
    )

    assert repository.mark_purge_not_eligible(document_id=DOCUMENT_ID) is None
    assert _stored(repository).purge_status is PurgeStatus.PURGED


def test_withdrawal_moves_an_eligible_document_back_to_not_eligible() -> None:
    """The state change itself, which the default masks.

    `purge_status` defaults to `not_eligible`, so a freshly stored document
    takes the idempotent early return and never exercises the write. This starts
    from `eligible` — the state a hold arriving after an eligibility decision
    actually has to reverse.
    """
    repository = _repository(
        purge_status=PurgeStatus.ELIGIBLE,
        legal_hold_status=LegalHoldStatus.ACTIVE,
        legal_hold_count=1,
    )

    withdrawn = repository.mark_purge_not_eligible(document_id=DOCUMENT_ID)

    assert withdrawn is not None
    assert withdrawn.purge_status is PurgeStatus.NOT_ELIGIBLE
    assert _stored(repository).purge_status is PurgeStatus.NOT_ELIGIBLE
    assert withdrawn.legal_hold_status is LegalHoldStatus.ACTIVE, (
        "withdrawal must not touch the hold columns it did not decide"
    )


def test_withdrawal_is_idempotent_when_already_not_eligible() -> None:
    repository = _repository(purge_status=PurgeStatus.NOT_ELIGIBLE)
    before = _stored(repository)

    withdrawn = repository.mark_purge_not_eligible(document_id=DOCUMENT_ID)

    assert withdrawn is not None
    assert withdrawn.updated_at == before.updated_at, (
        "an unchanged status must not churn the record"
    )


# --------------------------------------------------------------- completion


def test_completion_refuses_an_unknown_document() -> None:
    repository = InMemoryArchiveDocumentRepository()

    assert repository.complete_purge(document_id="doc_absent", purged_at=datetime.now(UTC)) is None


def test_completion_refuses_a_document_with_no_claimed_intent() -> None:
    """No path may record a destruction nobody ordered."""
    repository = _repository()

    assert repository.complete_purge(document_id=DOCUMENT_ID, purged_at=datetime.now(UTC)) is None
    assert _stored(repository).purged_at is None


def test_completion_is_idempotent_and_does_not_restamp() -> None:
    """A retry finishing an interrupted purge must not move when the bytes went."""
    started = datetime.now(UTC)
    repository = _repository(purge_started_at=started)

    first = repository.complete_purge(document_id=DOCUMENT_ID, purged_at=started)
    assert first is not None

    second = repository.complete_purge(
        document_id=DOCUMENT_ID, purged_at=started + timedelta(hours=1)
    )

    assert second is not None
    assert second.purged_at == first.purged_at


# ------------------------------------------------- refusal reclassification


def test_a_refused_transition_answers_from_the_stored_row_not_the_snapshot() -> None:
    """The service must report what the database holds, never the caller's stale read.

    The snapshot says `not_eligible` and no hold; the stored row has been purged
    by another writer since. Returning the snapshot would report a purge status
    the database does not hold, which is the class of lie the whole correction
    removes.
    """
    repository = _repository(
        purge_started_at=datetime.now(UTC),
        purged_at=datetime.now(UTC),
        purge_status=PurgeStatus.PURGED,
    )
    stale = _stored(repository).model_copy(
        update={
            "purge_status": PurgeStatus.NOT_ELIGIBLE,
            "purged_at": None,
            "purge_started_at": None,
        }
    )

    metadata, eligible, reason = evaluate_purge(repository, stale, TODAY)

    assert reason == "already_purged"
    assert eligible is True
    assert metadata.purge_status is PurgeStatus.PURGED


def test_a_refusal_under_a_concurrent_hold_reports_the_hold() -> None:
    repository = _repository(legal_hold_status=LegalHoldStatus.ACTIVE, legal_hold_count=1)
    stale = _stored(repository).model_copy(
        update={"legal_hold_status": LegalHoldStatus.CLEAR, "legal_hold_count": 0}
    )

    metadata, eligible, reason = evaluate_purge(
        repository, stale.model_copy(update={"retain_until_date": date(2020, 1, 1)}), TODAY
    )

    assert reason == "legal_hold_active"
    assert eligible is False
    assert metadata.legal_hold_status is LegalHoldStatus.ACTIVE


def test_a_refusal_on_a_started_purge_reports_it_as_completable() -> None:
    repository = _repository(purge_started_at=datetime.now(UTC))

    metadata, eligible, reason = reclassify_refused_transition(repository, DOCUMENT_ID)

    assert reason == "purge_in_progress"
    assert eligible is True
    assert metadata.purge_started_at is not None


def test_an_unexplained_refusal_is_never_eligible() -> None:
    """The branch that exists so a future guard cannot silently mean yes.

    No guard condition holds on this row, so a refusal here is a guard this
    classification does not know about. The caller is asking whether destruction
    is permitted, and a state the service cannot account for is not a yes.
    """
    repository = _repository()

    metadata, eligible, reason = reclassify_refused_transition(repository, DOCUMENT_ID)

    assert reason == "purge_state_changed"
    assert eligible is False
    assert metadata.purge_status is not PurgeStatus.PURGED


def test_reclassification_raises_when_the_document_is_gone() -> None:
    repository = InMemoryArchiveDocumentRepository()

    with pytest.raises(DocumentNotFoundError):
        reclassify_refused_transition(repository, "doc_absent")
