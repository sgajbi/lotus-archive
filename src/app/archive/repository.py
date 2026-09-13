from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Protocol

from app.archive.exceptions import (
    DocumentNotFoundError,
    DuplicateArchiveRequestConflict,
    HistoricalIntegrityError,
)
from app.archive.lifecycle_transitions import (
    transition_pointers_agree,
    validate_lifecycle_preconditions,
)
from app.archive.models import (
    LIFECYCLE_TARGET_ORIGIN_FIELD,
    LegalHoldStatus,
    ArchiveDocumentMetadata,
    LegalHoldRecord,
    LifecycleRelationshipRecord,
    LifecycleTransitionType,
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

    def release_and_record_legal_hold(
        self,
        *,
        document_id: str,
        legal_hold_id: str,
        released_by: str,
        released_at: datetime,
        release_reason: str,
    ) -> tuple[LegalHoldRecord, ArchiveDocumentMetadata] | None: ...

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

    def refresh_legal_hold_summary(
        self,
        document_id: str,
    ) -> ArchiveDocumentMetadata | None: ...

    def get_legal_hold(self, legal_hold_id: str) -> LegalHoldRecord | None: ...

    def list_legal_holds(self, document_id: str) -> list[LegalHoldRecord]: ...

    def apply_lifecycle_transition(
        self,
        *,
        source_document_id: str,
        target_document_id: str,
        transition_type: LifecycleTransitionType,
        relationship: LifecycleRelationshipRecord,
    ) -> tuple[
        LifecycleRelationshipRecord, ArchiveDocumentMetadata, ArchiveDocumentMetadata
    ]: ...

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
        """Create a document, or touch `updated_at` on an identical existing one.

        On an existing row this writes ONLY `updated_at`. Retention, hold and
        lifecycle columns move exclusively through their owning transitions
        (`begin_purge`, `admit_and_record_legal_hold`, `refresh_legal_hold_summary`,
        `apply_lifecycle_transition`, ...), so a caller snapshot handed to save()
        cannot revert state another writer committed since the snapshot was read
        (issue #166). Any other difference is refused, immutable identity and
        transition-owned posture alike.
        """
        existing_document_id = self._by_archive_request_id.get(metadata.archive_request_id)
        if existing_document_id and existing_document_id != metadata.document_id:
            raise DuplicateArchiveRequestConflict(
                "archive_request_id already belongs to another document"
            )
        existing = self._by_document_id.get(metadata.document_id)
        if existing is not None:
            changed = sorted(
                field
                for field in type(metadata).model_fields
                if field != "updated_at" and getattr(existing, field) != getattr(metadata, field)
            )
            if changed:
                raise HistoricalIntegrityError(
                    "document fields cannot change through save() after archival: "
                    + ", ".join(changed)
                )
            touched = existing.model_copy(update={"updated_at": metadata.updated_at})
            self._by_document_id[metadata.document_id] = touched
            return touched
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
        if self._active_hold_count(document_id):
            # Belt over the summary column: an active hold ROW vetoes
            # destruction even when a historic race left the summary saying
            # clear (issue #166 legacy drift).
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
        active_count = self._active_hold_count(document_id)
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

    def release_and_record_legal_hold(
        self,
        *,
        document_id: str,
        legal_hold_id: str,
        released_by: str,
        released_at: datetime,
        release_reason: str,
    ) -> tuple[LegalHoldRecord, ArchiveDocumentMetadata] | None:
        """Release the hold row and recount the summary as ONE step (issue #166).

        The mirror of `admit_and_record_legal_hold`. As two steps -- write the
        hold row, then refresh from a separate read -- the refresh raced a
        concurrent admission: it counted before the new hold committed and wrote
        its stale CLEAR/0 afterwards, which is exactly the summary `begin_purge`
        trusts. Releasing an already-released hold converges on the recorded
        release rather than restamping it.
        """
        if document_id not in self._by_document_id:
            return None
        hold = self._legal_holds.get(legal_hold_id)
        if hold is None or hold.document_id != document_id:
            return None
        if hold.hold_status is LegalHoldStatus.ACTIVE:
            hold = hold.model_copy(
                update={
                    "hold_status": LegalHoldStatus.CLEAR,
                    "released_by": released_by,
                    "released_at": released_at,
                    "release_reason": release_reason,
                }
            )
            self._legal_holds[legal_hold_id] = hold
        metadata = self.refresh_legal_hold_summary(document_id)
        if metadata is None:  # pragma: no cover - document presence checked above
            return None
        return hold, metadata

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
        if self._active_hold_count(document_id):
            # Belt over the summary column, mirroring begin_purge (issue #166).
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

    def refresh_legal_hold_summary(
        self,
        document_id: str,
    ) -> ArchiveDocumentMetadata | None:
        """Recount from the hold rows AT WRITE TIME, and write only those columns.

        The repository derives the status and count itself; no caller-computed
        summary is accepted as authority (issue #166). The previous port took a
        status and a count the service had derived from an earlier read, so a
        hold admitted between that read and this write was overwritten with the
        stale CLEAR/0 -- and `begin_purge` trusts exactly this column. In the
        database implementation the derivation and the write share one
        transaction under the document row lock.
        """
        existing = self._by_document_id.get(document_id)
        if existing is None:
            return None
        active_count = self._active_hold_count(document_id)
        status = LegalHoldStatus.ACTIVE if active_count else LegalHoldStatus.CLEAR
        if existing.legal_hold_status is status and existing.legal_hold_count == active_count:
            return existing
        updated = existing.model_copy(
            update={
                "legal_hold_status": status,
                "legal_hold_count": active_count,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._by_document_id[document_id] = updated
        return updated

    def seed_document_state(self, metadata: ArchiveDocumentMetadata) -> ArchiveDocumentMetadata:
        """Test seeding only: store a document snapshot VERBATIM, bypassing every
        transition guard. Not part of `ArchiveDocumentRepository` - exists so
        tests can construct the legacy and corrupted states the production
        writers refuse (drifted summaries, half-linked chains, cycles)."""
        self._by_document_id[metadata.document_id] = metadata
        self._by_archive_request_id[metadata.archive_request_id] = metadata.document_id
        return metadata

    def _active_hold_count(self, document_id: str) -> int:
        return sum(
            1
            for hold in self._legal_holds.values()
            if hold.document_id == document_id and hold.hold_status is LegalHoldStatus.ACTIVE
        )

    def save_legal_hold(self, legal_hold: LegalHoldRecord) -> LegalHoldRecord:
        """Test seeding only: writes a bare hold row with NO summary maintenance.

        Not part of `ArchiveDocumentRepository`. Production holds exist only
        through `admit_and_record_legal_hold` / `release_and_record_legal_hold`,
        which keep the row and the document summary in one step; this exists so
        tests can construct the adversarial states those methods refuse.
        """
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

    def apply_lifecycle_transition(
        self,
        *,
        source_document_id: str,
        target_document_id: str,
        transition_type: LifecycleTransitionType,
        relationship: LifecycleRelationshipRecord,
    ) -> tuple[LifecycleRelationshipRecord, ArchiveDocumentMetadata, ArchiveDocumentMetadata]:
        """Validate the STORED rows, then write only the columns this transition decides.

        The previous shape took two caller snapshots and saved them whole, so a
        purge or hold committed after the service's validation was overwritten
        by the stale snapshot -- PURGED with intent and purged_at was observed
        reverting to NOT_ELIGIBLE with both cleared (issue #166). Now the
        preconditions are re-validated against the stored rows and the writes
        touch `superseded_by_document_id`, the transition's origin field and
        `updated_at` only. The database implementation locks both document rows
        in deterministic id order first.

        An exact replay -- both stored pointers already record this transition
        and the relationship row exists -- converges on the recorded
        relationship instead of conflicting.
        """
        source = self._by_document_id.get(source_document_id)
        target = self._by_document_id.get(target_document_id)
        if source is None or target is None:
            raise DocumentNotFoundError("archive document was not found")
        if transition_pointers_agree(
            source=source, target=target, transition_type=transition_type
        ):
            for existing in self._lifecycle_relationships.values():
                if (
                    existing.source_document_id == source_document_id
                    and existing.target_document_id == target_document_id
                    and existing.transition_type is transition_type
                ):
                    return existing, source, target
        validate_lifecycle_preconditions(
            source=source, target=target, transition_type=transition_type
        )
        origin_field = LIFECYCLE_TARGET_ORIGIN_FIELD[transition_type]
        now = datetime.now(timezone.utc)
        updated_source = source.model_copy(
            update={"superseded_by_document_id": target_document_id, "updated_at": now}
        )
        updated_target = target.model_copy(
            update={origin_field: source_document_id, "updated_at": now}
        )
        self._by_document_id[source_document_id] = updated_source
        self._by_document_id[target_document_id] = updated_target
        self._lifecycle_relationships[relationship.lifecycle_relationship_id] = relationship
        return relationship, updated_source, updated_target

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
