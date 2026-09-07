"""Destruction is irreversible; the record of it must be durable first.

`purge_document` deleted the stored object and then recorded the outcome. A
failure between the two left a document whose metadata said retained and whose
bytes were gone — indistinguishable from a genuinely retained document, because
nothing anywhere reconciles storage against metadata.

The unrecoverable ordering is the reason this matters rather than being an
ordinary partial write:

1. purge executes, `storage.delete` succeeds, `repository.save` fails;
2. a legal hold is applied — legitimately, since the record says retained;
3. the retry now refuses with `legal_hold_active`, correctly, and can never
   complete;
4. Archive goes on issuing **signed** `LEGAL_HOLD` decisions asserting the
   evidence is preserved under hold, for evidence that no longer exists.

The operation succeeded, the service starts, the signature verifies, and the
assertion is false. `purge_started_at` is recorded before the delete so that
state is visible and the retry can always finish.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import AccessEventType, InMemoryAccessAuditRepository
from app.archive.commands import LegalHoldCreateCommand
from app.archive.exceptions import PurgeAlreadyStartedError
from app.archive.models import ArchiveDocumentMetadata, LegalHoldStatus, PurgeStatus
from app.archive.repository import InMemoryArchiveDocumentRepository
from app.archive.service import ArchiveDocumentService
from app.archive.storage import FilesystemObjectStorage
from app.security.caller_context import CallerContext
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


def _archived(
    service: ArchiveDocumentService, caller: CallerContext | None = None
) -> ArchiveDocumentMetadata:
    return service.create_document(
        command=_create_request(),
        caller_context=caller or _caller("lotus-render"),
        trace_id="trace-create",
    )


def _hold_command() -> LegalHoldCreateCommand:
    return LegalHoldCreateCommand(
        hold_reason="Regulatory review",
        authority_reference="REG-2026-01",
    )


def test_the_intent_is_recorded_before_the_object_is_deleted(tmp_path: Path) -> None:
    """The ordering claim, asserted at the moment it matters.

    The delete is made to fail, so nothing after it runs. If the intent were
    recorded afterwards — as it was — the document would still read as retained
    with no trace that destruction had been attempted.
    """

    service = _service(tmp_path)
    metadata = _archived(service)

    def exploding_delete(*, key: str) -> None:
        raise RuntimeError("object store unavailable")

    service.storage.delete = exploding_delete  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        service.purge_document(
            document_id=metadata.document_id,
            caller_context=_caller(),
            trace_id="trace-purge",
            evaluation_date=metadata.retain_until_date,
        )

    stored = service.repository.get_by_document_id(metadata.document_id)
    assert stored is not None
    assert stored.purge_started_at is not None, "destruction intent must survive the failure"
    assert stored.purge_status is not PurgeStatus.PURGED, "nothing was actually destroyed"


def test_a_purge_interrupted_after_deletion_can_still_be_completed(tmp_path: Path) -> None:
    """The failure the whole change exists for: bytes gone, outcome unrecorded.

    Interrupted at exactly that point — the delete succeeds, the save that would
    record `PURGED` raises. The retry must converge on a complete record rather
    than leaving the document reporting retained forever.
    """

    service = _service(tmp_path)
    metadata = _archived(service)
    real_save = service.repository.save

    def failing_completion_save(record):  # type: ignore[no-untyped-def]
        # Keyed on what is being written, not on how many saves have happened:
        # `_evaluate_purge` may save an ELIGIBLE transition first, so a
        # call-counting fake would interrupt the intent instead of the outcome
        # and quietly test the wrong failure.
        if record.purge_status is PurgeStatus.PURGED:
            raise RuntimeError("ledger write failed")
        return real_save(record)

    service.repository.save = failing_completion_save  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        service.purge_document(
            document_id=metadata.document_id,
            caller_context=_caller(),
            trace_id="trace-purge",
            evaluation_date=metadata.retain_until_date,
        )

    interrupted = service.repository.get_by_document_id(metadata.document_id)
    assert interrupted is not None
    assert interrupted.purge_started_at is not None
    assert not (tmp_path / "objects" / metadata.storage_key).exists(), "the bytes are gone"

    service.repository.save = real_save  # type: ignore[method-assign]
    completed, reason = service.purge_document(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="trace-purge-retry",
        evaluation_date=metadata.retain_until_date,
    )

    assert completed.purge_status is PurgeStatus.PURGED
    assert completed.purged_at is not None
    assert reason == "purged"


def test_a_hold_that_races_the_intent_cannot_strand_the_document(tmp_path: Path) -> None:
    """The unrecoverable ordering, and the reason the hold check moved.

    A hold applied after destruction began used to make the retry refuse with
    `legal_hold_active` permanently, leaving the document asserting
    retained-under-hold with its bytes destroyed. A started purge is now
    completable, because finishing the record is the only honest outcome once
    the object may already be gone.
    """

    service = _service(tmp_path)
    metadata = _archived(service)
    real_save = service.repository.save

    def failing_completion_save(record):  # type: ignore[no-untyped-def]
        # Keyed on what is being written, not on how many saves have happened:
        # `_evaluate_purge` may save an ELIGIBLE transition first, so a
        # call-counting fake would interrupt the intent instead of the outcome
        # and quietly test the wrong failure.
        if record.purge_status is PurgeStatus.PURGED:
            raise RuntimeError("ledger write failed")
        return real_save(record)

    service.repository.save = failing_completion_save  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        service.purge_document(
            document_id=metadata.document_id,
            caller_context=_caller(),
            trace_id="trace-purge",
            evaluation_date=metadata.retain_until_date,
        )
    service.repository.save = real_save  # type: ignore[method-assign]

    # A hold recorded directly, as one racing the intent would have been.
    stranded = service.repository.get_by_document_id(metadata.document_id)
    assert stranded is not None
    service.repository.save(
        stranded.model_copy(update={"legal_hold_status": LegalHoldStatus.ACTIVE})
    )

    completed, reason = service.purge_document(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="trace-purge-retry",
        evaluation_date=metadata.retain_until_date,
    )

    assert completed.purge_status is PurgeStatus.PURGED
    assert reason == "purged", "a started purge must not be strandable by a later hold"


def test_a_legal_hold_is_refused_once_destruction_has_started(tmp_path: Path) -> None:
    """A hold cannot preserve what is already being destroyed.

    Refused rather than recorded: accepting it would produce a document
    asserting held-and-preserved with its bytes gone, which reads as a clean
    green. The refusal precedes every effect — no hold record is written.
    """

    service = _service(tmp_path)
    metadata = _archived(service)

    def exploding_delete(*, key: str) -> None:
        raise RuntimeError("object store unavailable")

    service.storage.delete = exploding_delete  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        service.purge_document(
            document_id=metadata.document_id,
            caller_context=_caller(),
            trace_id="trace-purge",
            evaluation_date=metadata.retain_until_date,
        )

    with pytest.raises(PurgeAlreadyStartedError):
        service.set_legal_hold(
            document_id=metadata.document_id,
            command=_hold_command(),
            caller_context=_caller("lotus-report"),
            trace_id="trace-hold",
        )

    assert service.repository.list_legal_holds(metadata.document_id) == []
    denied = [
        event
        for event in service.audit_repository.list_by_document_id(metadata.document_id)
        if event.event_type == AccessEventType.LEGAL_HOLD_SET
    ]
    assert [event.operation_reason_code for event in denied] == ["purge_already_started"]


def test_a_hold_placed_before_any_purge_still_blocks_it(tmp_path: Path) -> None:
    """The control this change must not weaken.

    Making a started purge completable would be a hole if it also let a purge
    start under an existing hold. It does not: the hold is still evaluated
    before any intent is recorded, so nothing is destroyed and nothing is
    marked.
    """

    service = _service(tmp_path)
    metadata = _archived(service)
    service.set_legal_hold(
        document_id=metadata.document_id,
        command=_hold_command(),
        caller_context=_caller("lotus-report"),
        trace_id="trace-hold",
    )

    from app.archive.exceptions import LegalHoldActiveError

    with pytest.raises(LegalHoldActiveError):
        service.purge_document(
            document_id=metadata.document_id,
            caller_context=_caller(),
            trace_id="trace-purge",
            evaluation_date=metadata.retain_until_date,
        )

    stored = service.repository.get_by_document_id(metadata.document_id)
    assert stored is not None
    assert stored.purge_started_at is None, "no destruction intent may be recorded under a hold"
    assert (tmp_path / "objects" / metadata.storage_key).exists()


def test_an_identical_purge_retry_converges_without_a_second_destruction(
    tmp_path: Path,
) -> None:
    """Replay: the same call twice yields one destruction and an audited outcome."""

    service = _service(tmp_path)
    metadata = _archived(service)
    deletes: list[str] = []
    real_delete = service.storage.delete

    def counting_delete(*, key: str) -> None:
        deletes.append(key)
        real_delete(key=key)

    service.storage.delete = counting_delete  # type: ignore[method-assign]

    first, first_reason = service.purge_document(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="trace-purge",
        evaluation_date=metadata.retain_until_date,
    )
    second, second_reason = service.purge_document(
        document_id=metadata.document_id,
        caller_context=_caller(),
        trace_id="trace-purge-again",
        evaluation_date=metadata.retain_until_date,
    )

    assert first_reason == "purged"
    assert second_reason == "already_purged"
    assert deletes == [metadata.storage_key], "the object is destroyed once, not twice"
    assert second.purged_at == first.purged_at, "the recorded instant must not move on replay"
    assert second.purge_started_at == first.purge_started_at


def test_the_purged_record_survives_a_service_restart(tmp_path: Path) -> None:
    """Persistence: a new service over the same repository reads the same outcome.

    The lifecycle assertion Archive signs is derived from this record, so a
    restart that lost `purge_started_at` or `purged_at` would let the false
    retained-under-hold reading return by another route.
    """

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
        trace_id="trace-purge",
        evaluation_date=metadata.retain_until_date,
    )

    restarted = ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=audit,
    )
    after_restart = restarted.get_lifecycle_posture(metadata.document_id)

    assert after_restart.purge_status is PurgeStatus.PURGED
    assert after_restart.purged_at == purged.purged_at
    assert after_restart.purge_started_at == purged.purge_started_at
