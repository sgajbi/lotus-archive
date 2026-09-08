from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Protocol

from app.archive.exceptions import DuplicateArchiveRequestConflict, HistoricalIntegrityError
from app.archive.models import (
    LegalHoldStatus,
    MUTABLE_DOCUMENT_FIELDS,
    ArchiveDocumentMetadata,
    LegalHoldRecord,
    LifecycleRelationshipRecord,
    PurgeStatus,
)


@dataclass(frozen=True)
class ArchiveDocumentBatchLookup:
    documents: Mapping[str, ArchiveDocumentMetadata]
    unavailable_document_ids: frozenset[str] = frozenset()


class ArchiveDocumentRepository(Protocol):
    def check_ready(self) -> None: ...

    def get_by_document_id(self, document_id: str) -> ArchiveDocumentMetadata | None: ...

    def get_by_document_ids(
        self,
        document_ids: tuple[str, ...],
    ) -> ArchiveDocumentBatchLookup: ...

    def get_by_checksum(self, checksum: str) -> list[ArchiveDocumentMetadata]: ...

    def get_by_archive_request_id(
        self,
        archive_request_id: str,
    ) -> ArchiveDocumentMetadata | None: ...

    def save(self, metadata: ArchiveDocumentMetadata) -> ArchiveDocumentMetadata: ...

    def begin_purge(
        self,
        *,
        document_id: str,
        started_at: datetime,
    ) -> ArchiveDocumentMetadata | None: ...

    def admit_and_record_legal_hold(
        self,
        *,
        document_id: str,
        legal_hold: LegalHoldRecord,
    ) -> ArchiveDocumentMetadata | None: ...

    def mark_purge_eligible(
        self,
        *,
        document_id: str,
        eligible_at: datetime,
    ) -> ArchiveDocumentMetadata | None: ...

    def mark_purge_not_eligible(
        self,
        *,
        document_id: str,
    ) -> ArchiveDocumentMetadata | None: ...

    def complete_purge(
        self,
        *,
        document_id: str,
        purged_at: datetime,
    ) -> ArchiveDocumentMetadata | None: ...

    def update_legal_hold_summary(
        self,
        *,
        document_id: str,
        legal_hold_status: LegalHoldStatus,
        legal_hold_count: int,
    ) -> ArchiveDocumentMetadata | None: ...

    def save_legal_hold(self, legal_hold: LegalHoldRecord) -> LegalHoldRecord: ...

    def get_legal_hold(self, legal_hold_id: str) -> LegalHoldRecord | None: ...

    def list_legal_holds(self, document_id: str) -> list[LegalHoldRecord]: ...

    def save_lifecycle_relationship(
        self,
        relationship: LifecycleRelationshipRecord,
    ) -> LifecycleRelationshipRecord: ...

    def apply_lifecycle_transition(
        self,
        source: ArchiveDocumentMetadata,
        target: ArchiveDocumentMetadata,
        relationship: LifecycleRelationshipRecord,
    ) -> LifecycleRelationshipRecord: ...

    def delete_lifecycle_relationship(self, lifecycle_relationship_id: str) -> None: ...

    def list_lifecycle_relationships(
        self,
        document_id: str,
    ) -> list[LifecycleRelationshipRecord]: ...


class InMemoryArchiveDocumentRepository:
    def __init__(self) -> None:
        self._by_document_id: dict[str, ArchiveDocumentMetadata] = {}
        self._by_archive_request_id: dict[str, str] = {}
        self._legal_holds: dict[str, LegalHoldRecord] = {}
        self._lifecycle_relationships: dict[str, LifecycleRelationshipRecord] = {}

    def check_ready(self) -> None:
        return None

    def get_by_document_id(self, document_id: str) -> ArchiveDocumentMetadata | None:
        return self._by_document_id.get(document_id)

    def get_by_document_ids(
        self,
        document_ids: tuple[str, ...],
    ) -> ArchiveDocumentBatchLookup:
        return ArchiveDocumentBatchLookup(
            documents={
                document_id: self._by_document_id[document_id]
                for document_id in document_ids
                if document_id in self._by_document_id
            }
        )

    def get_by_archive_request_id(
        self,
        archive_request_id: str,
    ) -> ArchiveDocumentMetadata | None:
        document_id = self._by_archive_request_id.get(archive_request_id)
        if document_id is None:
            return None
        return self._by_document_id[document_id]

    def get_by_checksum(self, checksum: str) -> list[ArchiveDocumentMetadata]:
        return [
            metadata for metadata in self._by_document_id.values() if metadata.checksum == checksum
        ]

    def save(self, metadata: ArchiveDocumentMetadata) -> ArchiveDocumentMetadata:
        existing_document_id = self._by_archive_request_id.get(metadata.archive_request_id)
        if existing_document_id and existing_document_id != metadata.document_id:
            raise DuplicateArchiveRequestConflict(
                "archive_request_id already belongs to another document"
            )
        existing = self._by_document_id.get(metadata.document_id)
        if existing is not None:
            changed_immutable = sorted(
                field
                for field in type(metadata).model_fields
                if field not in MUTABLE_DOCUMENT_FIELDS
                and getattr(existing, field) != getattr(metadata, field)
            )
            if changed_immutable:
                raise HistoricalIntegrityError(
                    "immutable document fields cannot change after archival: "
                    + ", ".join(changed_immutable)
                )
        self._by_document_id[metadata.document_id] = metadata
        self._by_archive_request_id[metadata.archive_request_id] = metadata.document_id
        return metadata

    def begin_purge(
        self,
        *,
        document_id: str,
        started_at: datetime,
    ) -> ArchiveDocumentMetadata | None:
        """Claim the right to destroy, or return None because someone else holds it.

        The condition and the write are one step. Reading the state, deciding,
        and then saving a snapshot is what let a concurrent hold erase a
        completed purge: the decision was correct at the instant it was taken
        and the write that followed it enforced nothing.
        """
        existing = self._by_document_id.get(document_id)
        if existing is None:
            return None
        if existing.purge_started_at is not None:
            return existing
        if existing.legal_hold_status is LegalHoldStatus.ACTIVE:
            return None
        claimed = existing.model_copy(
            update={"purge_started_at": started_at, "updated_at": started_at}
        )
        self._by_document_id[document_id] = claimed
        return claimed

    def admit_and_record_legal_hold(
        self,
        *,
        document_id: str,
        legal_hold: LegalHoldRecord,
    ) -> ArchiveDocumentMetadata | None:
        """Admit, persist the hold and refresh the summary as ONE step.

        Previously three: admit committed `active`, then the hold row was
        inserted, then the summary was recounted. Between the first and second a
        competing purge recounted, found **zero** hold rows, cleared `active` and
        deleted the object -- after which the hold row landed and the caller was
        told their hold succeeded. The observed end state was PURGED metadata,
        one ACTIVE hold record and absent bytes, and the lifecycle-action
        function then answered LEGAL_HOLD over a destroyed document.

        No window exists now: the recount happens with the row already present,
        and in the database implementation all three writes commit together.
        """
        existing = self._by_document_id.get(document_id)
        if existing is None or existing.purge_started_at is not None:
            return None
        self._legal_holds[legal_hold.legal_hold_id] = legal_hold
        active_count = sum(
            1
            for hold in self._legal_holds.values()
            if hold.document_id == document_id and hold.hold_status is LegalHoldStatus.ACTIVE
        )
        now = datetime.now(timezone.utc)
        admitted = existing.model_copy(
            update={
                "legal_hold_status": LegalHoldStatus.ACTIVE,
                "legal_hold_count": active_count,
                "updated_at": now,
            }
        )
        self._by_document_id[document_id] = admitted
        return admitted

    def mark_purge_eligible(
        self,
        *,
        document_id: str,
        eligible_at: datetime,
    ) -> ArchiveDocumentMetadata | None:
        """Grant eligibility, refusing when another writer holds a stronger claim.

        Eligibility is the transition that grants permission to destroy, so it
        carries the hold guard as well as the irreversibility guards. An
        eligibility decision taken from a snapshot and written back wholesale is
        how a committed hold's summary was overwritten and the document deleted
        with an ACTIVE hold record against it.
        """
        existing = self._by_document_id.get(document_id)
        if existing is None:
            return None
        if existing.purge_started_at is not None or existing.purge_status is PurgeStatus.PURGED:
            return None
        if existing.legal_hold_status is LegalHoldStatus.ACTIVE:
            return None
        now = datetime.now(timezone.utc)
        updated = existing.model_copy(
            update={
                "purge_status": PurgeStatus.ELIGIBLE,
                "purge_eligible_at": existing.purge_eligible_at or eligible_at,
                "updated_at": now,
            }
        )
        self._by_document_id[document_id] = updated
        return updated

    def mark_purge_not_eligible(
        self,
        *,
        document_id: str,
    ) -> ArchiveDocumentMetadata | None:
        """Withdraw eligibility. Strictly protective, so it carries no hold guard.

        This is the transition taken *because* a hold is active, so requiring
        the absence of one would refuse the case it exists to serve. It still
        refuses to touch a started or completed purge: withdrawing eligibility
        from a document whose bytes are already gone would rewrite history to
        say destruction was never permitted.
        """
        existing = self._by_document_id.get(document_id)
        if existing is None:
            return None
        if existing.purge_started_at is not None or existing.purge_status is PurgeStatus.PURGED:
            return None
        if existing.purge_status is PurgeStatus.NOT_ELIGIBLE:
            return existing
        now = datetime.now(timezone.utc)
        updated = existing.model_copy(
            update={"purge_status": PurgeStatus.NOT_ELIGIBLE, "updated_at": now}
        )
        self._by_document_id[document_id] = updated
        return updated

    def complete_purge(
        self,
        *,
        document_id: str,
        purged_at: datetime,
    ) -> ArchiveDocumentMetadata | None:
        """Record destruction against the stored row, never from a snapshot.

        Only reachable behind a claimed intent, so it requires one: completing a
        purge that was never begun would assert a destruction no writer ordered.
        Idempotent on an already-purged row so an interrupted purge can be
        retried to completion.
        """
        existing = self._by_document_id.get(document_id)
        if existing is None or existing.purge_started_at is None:
            return None
        if existing.purge_status is PurgeStatus.PURGED:
            return existing
        now = datetime.now(timezone.utc)
        updated = existing.model_copy(
            update={
                "purge_status": PurgeStatus.PURGED,
                "purged_at": purged_at,
                "updated_at": now,
            }
        )
        self._by_document_id[document_id] = updated
        return updated

    def update_legal_hold_summary(
        self,
        *,
        document_id: str,
        legal_hold_status: LegalHoldStatus,
        legal_hold_count: int,
    ) -> ArchiveDocumentMetadata | None:
        """Write ONLY the hold columns, against the row as it is stored now.

        The caller cannot pass a snapshot here, so it cannot write one back. The
        previous form re-serialised a whole document the caller had read
        earlier, which is how a concurrent purge's `purge_status`,
        `purge_started_at` and `purged_at` were silently reverted.
        """
        existing = self._by_document_id.get(document_id)
        if existing is None:
            return None
        updated = existing.model_copy(
            update={
                "legal_hold_status": legal_hold_status,
                "legal_hold_count": legal_hold_count,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._by_document_id[document_id] = updated
        return updated

    def save_legal_hold(self, legal_hold: LegalHoldRecord) -> LegalHoldRecord:
        self._legal_holds[legal_hold.legal_hold_id] = legal_hold
        return legal_hold

    def get_legal_hold(self, legal_hold_id: str) -> LegalHoldRecord | None:
        return self._legal_holds.get(legal_hold_id)

    def list_legal_holds(self, document_id: str) -> list[LegalHoldRecord]:
        return [
            legal_hold
            for legal_hold in self._legal_holds.values()
            if legal_hold.document_id == document_id
        ]

    def save_lifecycle_relationship(
        self,
        relationship: LifecycleRelationshipRecord,
    ) -> LifecycleRelationshipRecord:
        self._lifecycle_relationships[relationship.lifecycle_relationship_id] = relationship
        return relationship

    def apply_lifecycle_transition(
        self,
        source: ArchiveDocumentMetadata,
        target: ArchiveDocumentMetadata,
        relationship: LifecycleRelationshipRecord,
    ) -> LifecycleRelationshipRecord:
        """All three writes or none. A half-linked supersession chain is unrepairable through
        the API - the validation guards would reject every retry - so the unit is atomic.
        In-memory atomicity is snapshot-and-restore; the restore is pure dict assignment and
        cannot itself fail."""
        snapshot = {
            document.document_id: document
            for document in (
                self._by_document_id.get(source.document_id),
                self._by_document_id.get(target.document_id),
            )
            if document is not None
        }
        self.save(source)
        try:
            self.save(target)
        except Exception:
            for document_id, document in snapshot.items():
                self._by_document_id[document_id] = document
            raise
        self._lifecycle_relationships[relationship.lifecycle_relationship_id] = relationship
        return relationship

    def delete_lifecycle_relationship(self, lifecycle_relationship_id: str) -> None:
        self._lifecycle_relationships.pop(lifecycle_relationship_id, None)

    def list_lifecycle_relationships(
        self,
        document_id: str,
    ) -> list[LifecycleRelationshipRecord]:
        return [
            relationship
            for relationship in self._lifecycle_relationships.values()
            if relationship.source_document_id == document_id
            or relationship.target_document_id == document_id
        ]
