"""Purge intent and legal-hold admission must be mutually exclusive (C5-ARC-01).

`#145` made the *crash* ordering safe: intent is recorded before the object is
deleted, so an interrupted purge is completable. It left the *concurrent*
transition unsafe.

`set_legal_hold` read the document, checked `purge_started_at` on that snapshot,
and finished by writing the snapshot back through `_refresh_legal_hold_summary`,
which updated three fields and re-serialised everything else. A purge committing
in between was erased wholesale. Measured before the fix:

    purge_status      : not_eligible      <- not even 'eligible'
    purge_started_at  : None
    purged_at         : None
    legal_hold_status : active
    object on disk    : False

The record asserted preserved-under-legal-hold, with no destruction intent ever
recorded, over bytes that were already gone -- and Archive would go on issuing
signed LEGAL_HOLD decisions about it. The refusal was correct at the instant it
ran and unenforced by the write that followed it.

Both operations now claim the document through a single conditional transition,
so the store decides the race and the loser observes the winner's committed
state rather than its own stale read.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import InMemoryAccessAuditRepository
from app.archive.commands import LegalHoldCreateCommand
from app.archive.exceptions import LegalHoldActiveError, PurgeAlreadyStartedError
from app.archive.models import (
    ArchiveDocumentMetadata,
    LegalHoldRecord,
    LegalHoldStatus,
    PurgeStatus,
)
from app.archive.repository import InMemoryArchiveDocumentRepository
from app.archive.service import ArchiveDocumentService
from app.archive.storage import FilesystemObjectStorage
from tests.unit.test_archive_document_service import _caller, _create_request


def _service(tmp_path: Path) -> ArchiveDocumentService:
    repository = InMemoryArchiveDocumentRepository()
    storage = FilesystemObjectStorage(tmp_path / "objects")
    return ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=InMemoryAccessAuditRepository(),
    )


def _archived(service: ArchiveDocumentService) -> ArchiveDocumentMetadata:
    return service.create_document(
        command=_create_request(), caller_context=_caller("lotus-render"), trace_id="t-create"
    )


def _hold() -> LegalHoldCreateCommand:
    return LegalHoldCreateCommand(
        hold_reason="Regulatory review", authority_reference="REG-2026-01"
    )


def test_a_purge_committing_mid_hold_is_not_erased(tmp_path: Path) -> None:
    """The C5-ARC-01 interleaving itself, at the exact point it used to corrupt.

    The purge is driven to completion after `set_legal_hold` has begun and
    immediately before its write-back. The hold must lose and say so; what it
    must never do is succeed and leave the record claiming preservation.
    """
    service = _service(tmp_path)
    metadata = _archived(service)
    repository = service.repository
    real_list = repository.list_legal_holds
    fired = {"done": False}

    def list_then_purge(document_id: str):  # type: ignore[no-untyped-def]
        result = real_list(document_id)
        if not fired["done"]:
            fired["done"] = True
            service.purge_document(
                document_id=metadata.document_id,
                caller_context=_caller(),
                trace_id="t-purge",
                evaluation_date=metadata.retain_until_date,
            )
        return result

    repository.list_legal_holds = list_then_purge  # type: ignore[method-assign]

    with pytest.raises(PurgeAlreadyStartedError):
        service.set_legal_hold(
            document_id=metadata.document_id,
            command=_hold(),
            caller_context=_caller("lotus-report"),
            trace_id="t-hold",
        )

    final = repository.get_by_document_id(metadata.document_id)
    assert final is not None
    assert final.purge_status is PurgeStatus.PURGED, "the committed purge must survive"
    assert final.purge_started_at is not None, "destruction intent must not be erased"
    assert final.purged_at is not None
    assert final.legal_hold_status is LegalHoldStatus.CLEAR, (
        "a refused hold must not leave the document claiming preservation"
    )
    assert repository.list_legal_holds(metadata.document_id) == []
    assert not (tmp_path / "objects" / metadata.storage_key).exists()


def test_purge_wins_when_it_claims_first(tmp_path: Path) -> None:
    """Intent acquired, hold refused, no hold record written."""
    service = _service(tmp_path)
    metadata = _archived(service)
    service.purge_document(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="t-purge",
        evaluation_date=metadata.retain_until_date,
    )

    with pytest.raises(PurgeAlreadyStartedError):
        service.set_legal_hold(
            document_id=metadata.document_id,
            command=_hold(),
            caller_context=_caller("lotus-report"),
            trace_id="t-hold",
        )

    assert service.repository.list_legal_holds(metadata.document_id) == []


def test_hold_wins_when_it_claims_first(tmp_path: Path) -> None:
    """The other direction, and the control this change must not weaken.

    A hold admitted first must block the purge outright — and, critically, must
    leave no destruction intent behind. A refused purge that still stamped
    `purge_started_at` would poison every later hold on a document nothing ever
    destroyed.
    """
    service = _service(tmp_path)
    metadata = _archived(service)
    service.set_legal_hold(
        document_id=metadata.document_id,
        command=_hold(),
        caller_context=_caller("lotus-report"),
        trace_id="t-hold",
    )

    with pytest.raises(LegalHoldActiveError):
        service.purge_document(
            document_id=metadata.document_id,
            caller_context=_caller(),
            trace_id="t-purge",
            evaluation_date=metadata.retain_until_date,
        )

    final = service.repository.get_by_document_id(metadata.document_id)
    assert final is not None
    assert final.purge_started_at is None, "a refused purge must record no intent"
    assert final.legal_hold_status is LegalHoldStatus.ACTIVE
    assert (tmp_path / "objects" / metadata.storage_key).exists(), "nothing was destroyed"


def test_a_hold_admitted_between_evaluation_and_intent_still_blocks_the_purge(
    tmp_path: Path,
) -> None:
    """The mirror interleaving: the hold commits after the purge evaluated it as clear.

    `_evaluate_purge` sees no hold and returns eligible; the hold is admitted
    before the intent is claimed. The conditional claim is what catches this —
    a purge that decided on its earlier read would delete an object under an
    active hold.
    """
    service = _service(tmp_path)
    metadata = _archived(service)
    repository = service.repository
    real_evaluate = service._evaluate_purge
    fired = {"done": False}

    def evaluate_then_hold(md, evaluation_date):  # type: ignore[no-untyped-def]
        result = real_evaluate(md, evaluation_date)
        if not fired["done"]:
            fired["done"] = True
            service.set_legal_hold(
                document_id=metadata.document_id,
                command=_hold(),
                caller_context=_caller("lotus-report"),
                trace_id="t-hold",
            )
        return result

    service._evaluate_purge = evaluate_then_hold  # type: ignore[method-assign]

    with pytest.raises(LegalHoldActiveError):
        service.purge_document(
            document_id=metadata.document_id,
            caller_context=_caller(),
            trace_id="t-purge",
            evaluation_date=metadata.retain_until_date,
        )

    final = repository.get_by_document_id(metadata.document_id)
    assert final is not None
    assert final.purge_started_at is None
    assert final.legal_hold_status is LegalHoldStatus.ACTIVE
    assert (tmp_path / "objects" / metadata.storage_key).exists(), (
        "an object under an admitted hold must not be deleted"
    )


def test_an_interrupted_purge_is_still_completable_after_the_change(tmp_path: Path) -> None:
    """#145's crash guarantee must survive the serialization.

    The claim is idempotent on re-entry: an intent already held returns the
    current row rather than refusing, so the retry finishes the record instead
    of stranding a document whose bytes are gone.
    """
    service = _service(tmp_path)
    metadata = _archived(service)
    real_save = service.repository.save

    def fail_completion(record: ArchiveDocumentMetadata) -> ArchiveDocumentMetadata:
        if record.purge_status is PurgeStatus.PURGED:
            raise RuntimeError("ledger write failed")
        return real_save(record)

    service.repository.save = fail_completion  # type: ignore[assignment,method-assign]
    with pytest.raises(RuntimeError):
        service.purge_document(
            document_id=metadata.document_id,
            caller_context=_caller(),
            trace_id="t-purge",
            evaluation_date=metadata.retain_until_date,
        )
    service.repository.save = real_save  # type: ignore[method-assign]

    completed, reason = service.purge_document(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="t-purge-retry",
        evaluation_date=metadata.retain_until_date,
    )

    assert completed.purge_status is PurgeStatus.PURGED
    assert reason == "purged"


def test_the_committed_state_survives_a_restart(tmp_path: Path) -> None:
    """Restart reads what was committed, not what any writer was holding."""
    repository = InMemoryArchiveDocumentRepository()
    storage = FilesystemObjectStorage(tmp_path / "objects")
    audit = InMemoryAccessAuditRepository()
    service = ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=audit,
    )
    metadata = _archived(service)
    purged, _ = service.purge_document(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="t-purge",
        evaluation_date=metadata.retain_until_date,
    )

    restarted = ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=audit,
    )
    after = restarted.get_lifecycle_posture(metadata.document_id)

    assert after.purge_status is PurgeStatus.PURGED
    assert after.purge_started_at == purged.purge_started_at
    assert after.purged_at == purged.purged_at
    assert after.legal_hold_status is LegalHoldStatus.CLEAR


def test_the_summary_refresh_cannot_revert_committed_purge_state(tmp_path: Path) -> None:
    """The second half of the fix, exercised directly at its own contract.

    The conditional claims mean no service path currently reaches this method
    with a stale snapshot -- so the guarantee would otherwise be asserted by
    construction and proven by nothing. Called here with a deliberately stale
    snapshot and a hold record that makes the counters disagree, which is the
    only condition under which it writes.

    Under the previous whole-row form this reverted `purge_status`,
    `purge_started_at` and `purged_at` to the snapshot's values. The repository
    method now takes no metadata at all, so a caller cannot hand it one to
    write back.
    """
    service = _service(tmp_path)
    metadata = _archived(service)
    stale = service.repository.get_by_document_id(metadata.document_id)
    assert stale is not None and stale.purge_started_at is None

    purged, _ = service.purge_document(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="t-purge",
        evaluation_date=metadata.retain_until_date,
    )
    assert purged.purge_status is PurgeStatus.PURGED

    # A hold record exists in the store, so the recount disagrees with the
    # stale snapshot and the method performs a write.
    service.repository.save_legal_hold(
        LegalHoldRecord(
            legal_hold_id="hold_stale_writer",
            document_id=metadata.document_id,
            hold_reason="Regulatory review",
            authority_reference="REG-2026-01",
            requested_by="compliance-officer",
        )
    )

    service._refresh_legal_hold_summary(stale)

    final = service.repository.get_by_document_id(metadata.document_id)
    assert final is not None
    assert final.purge_status is PurgeStatus.PURGED, "a stale writer must not revert the purge"
    assert final.purge_started_at == purged.purge_started_at
    assert final.purged_at == purged.purged_at
    assert final.legal_hold_status is LegalHoldStatus.ACTIVE, "the hold counters still update"
    assert final.legal_hold_count == 1


def test_the_claims_refuse_an_unknown_document(tmp_path: Path) -> None:
    """A document that is not there is not claimable, and not an error either.

    Reachable in the deployed shape: a caller can present an id that was never
    archived, or one removed between two calls. Returning None keeps the caller
    on its refusal path instead of raising from inside a conditional write.
    """
    repository = InMemoryArchiveDocumentRepository()

    assert repository.begin_purge(document_id="doc_absent", started_at=datetime.now(UTC)) is None
    assert repository.admit_legal_hold(document_id="doc_absent") is None
    assert (
        repository.update_legal_hold_summary(
            document_id="doc_absent",
            legal_hold_status=LegalHoldStatus.ACTIVE,
            legal_hold_count=1,
        )
        is None
    )
