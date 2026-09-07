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

    def admit_legal_hold(self, *, document_id: str) -> ArchiveDocumentMetadata | None: ...

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

    def admit_legal_hold(self, *, document_id: str) -> ArchiveDocumentMetadata | None:
        """Claim the document for preservation, or return None because destruction began.

        Contends on the same row as `begin_purge`, so exactly one of the two
        wins and the loser sees the winner's committed state rather than its own
        stale read.
        """
        existing = self._by_document_id.get(document_id)
        if existing is None:
            return None
        if existing.purge_started_at is not None:
            return None
        admitted = existing.model_copy(
            update={
                "legal_hold_status": LegalHoldStatus.ACTIVE,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._by_document_id[document_id] = admitted
        return admitted

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
