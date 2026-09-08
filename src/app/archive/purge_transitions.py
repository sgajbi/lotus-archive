"""Purge eligibility decided against the stored row, never a caller snapshot.

Extracted from `ArchiveService` because these three functions are one idea --
how a retention decision is committed when other writers are contending for the
same document -- and because the service module had grown past the point where
that idea was findable inside it.

The rule the whole module exists to hold: **a transition writes only the columns
it decides, and refuses rather than overwriting state another writer already
committed.** Reading a document, deciding, and saving the whole snapshot back is
what allowed an eligibility decision to erase a committed legal hold and a
completed purge alike -- the decision was correct at the instant it was taken,
and the write that followed enforced nothing.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.archive.exceptions import DocumentNotFoundError
from app.archive.models import ArchiveDocumentMetadata, LegalHoldStatus, PurgeStatus
from app.archive.repository import ArchiveDocumentRepository

PurgeEvaluation = tuple[ArchiveDocumentMetadata, bool, str]


def evaluate_purge(
    repository: ArchiveDocumentRepository,
    metadata: ArchiveDocumentMetadata,
    evaluation_date: date | None,
) -> PurgeEvaluation:
    """Classify a document for destruction, committing the resulting transition."""
    if metadata.purge_status is PurgeStatus.PURGED:
        return metadata, True, "already_purged"
    if metadata.purge_started_at is not None:
        # Destruction was already begun under an authorized decision, so the
        # object may be gone. The only completable outcome is to finish the
        # record. Refusing here -- for a hold that raced the intent -- would
        # strand the document reporting retained-under-hold with its bytes
        # destroyed, which is a false assurance rather than a safe refusal.
        return metadata, True, "purge_in_progress"
    if metadata.legal_hold_status is LegalHoldStatus.ACTIVE:
        return withdraw_eligibility(repository, metadata, "legal_hold_active")
    if metadata.retain_until_date is None:
        return withdraw_eligibility(repository, metadata, "retain_until_date_missing")
    effective_date = evaluation_date or date.today()
    if metadata.retain_until_date > effective_date:
        return withdraw_eligibility(repository, metadata, "retention_period_active")
    if metadata.purge_status is PurgeStatus.ELIGIBLE:
        # Re-evaluating an already-eligible document changes nothing; rewriting
        # updated_at here would churn the record without a state change.
        return metadata, True, "retention_elapsed"
    granted = repository.mark_purge_eligible(
        document_id=metadata.document_id,
        eligible_at=datetime.now(timezone.utc),
    )
    if granted is None:
        return reclassify_refused_transition(repository, metadata.document_id)
    return granted, True, "retention_elapsed"


def withdraw_eligibility(
    repository: ArchiveDocumentRepository,
    metadata: ArchiveDocumentMetadata,
    reason_code: str,
) -> PurgeEvaluation:
    """Withdraw eligibility against the stored row, never from a snapshot."""
    withdrawn = repository.mark_purge_not_eligible(document_id=metadata.document_id)
    if withdrawn is None:
        return reclassify_refused_transition(repository, metadata.document_id)
    return withdrawn, False, reason_code


def reclassify_refused_transition(
    repository: ArchiveDocumentRepository,
    document_id: str,
) -> PurgeEvaluation:
    """Answer from the stored row when a guarded transition refused.

    A refusal is not an error. It means another writer committed state this
    transition must not overwrite, so the decision taken from the caller's
    snapshot is out of date. Re-reading and classifying the stored row is the
    only truthful answer available -- returning the caller's snapshot would
    report a purge status the database does not hold, which is the class of lie
    this module exists to remove.

    Total over the guard conditions: `mark_purge_eligible` refuses on a started
    purge, a completed purge or an active hold, and `mark_purge_not_eligible` on
    the first two. Each has a branch here.
    """
    current = repository.get_by_document_id(document_id)
    if current is None:
        raise DocumentNotFoundError("archive document was not found")
    if current.purge_status is PurgeStatus.PURGED:
        return current, True, "already_purged"
    if current.purge_started_at is not None:
        return current, True, "purge_in_progress"
    if current.legal_hold_status is LegalHoldStatus.ACTIVE:
        return current, False, "legal_hold_active"
    # No guard condition holds, so a guard gained a case without a branch here.
    # Refuse rather than guess: the caller is asking whether destruction is
    # permitted, and a state this function cannot explain is not a yes.
    return current, False, "purge_state_changed"
