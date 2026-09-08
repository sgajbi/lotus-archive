from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64DecodeError
from collections.abc import Callable
from datetime import date, datetime, timezone
from uuid import uuid4

from app.archive.commands import (
    ArchiveDocumentCreateCommand,
    LegalHoldCreateCommand,
    LifecycleTransitionCommand,
)
from app.archive.access_preflight import (
    MAX_PREFLIGHT_DOCUMENT_IDS,
    ArchiveAccessPreflightItem,
    ArchiveAccessPreflightResult,
    ArchiveAccessReasonCode,
    ArchiveAccessResultState,
    ArchiveAccessState,
    preflight_item,
    result_state_for_items,
)
from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import (
    AccessAuditEvent,
    AccessAuditRepository,
    AccessEventType,
    AuthorizationDecision,
    access_audit_event,
)
from app.archive.authorization import (
    ArchiveAuthorizationPolicy,
    ArchivePermission,
    require_caller_scope,
)
from app.archive.checksum import calculate_checksum
from app.archive.exceptions import (
    ArchiveDocumentLookupUnavailableError,
    DocumentChecksumMismatchError,
    DocumentNotFoundError,
    LegalHoldActiveError,
    LegalHoldNotFoundError,
    MetadataValidationError,
    PurgeAlreadyStartedError,
    PurgeNotEligibleError,
    StorageReadFailedError,
    SupersessionConflictError,
    UnsupportedLifecycleTransitionError,
)
from app.archive.metrics import archive_metric
from app.archive.models import (
    LIFECYCLE_TARGET_ORIGIN_FIELD,
    LIFECYCLE_TRANSITION_REASON_CODES,
    ArchiveDocumentMetadata,
    LegalHoldRecord,
    LegalHoldStatus,
    LifecycleRelationshipRecord,
    LifecycleTransitionType,
    PurgeStatus,
)
from app.archive.purge_transitions import evaluate_purge
from app.archive.repository import ArchiveDocumentRepository
from app.archive.service_readiness import (
    ArchiveRuntimeReadiness,
    dependency_is_ready,
)
from app.archive.source_events import build_archive_document_source_events
from app.archive.storage import ObjectStorage
from app.security.caller_context import CallerContext


class ArchiveDocumentService:
    def __init__(
        self,
        *,
        writer: ArchiveWriter,
        repository: ArchiveDocumentRepository,
        storage: ObjectStorage,
        audit_repository: AccessAuditRepository,
        authorization_policy: ArchiveAuthorizationPolicy | None = None,
        max_decoded_document_bytes: int = 10 * 1024 * 1024,
        on_close: tuple[Callable[[], None], ...] = (),
    ) -> None:
        self.writer = writer
        self.repository = repository
        self.storage = storage
        self.audit_repository = audit_repository
        self.authorization_policy = authorization_policy or ArchiveAuthorizationPolicy()
        self._on_close = on_close
        self.max_decoded_document_bytes = max_decoded_document_bytes

    def runtime_readiness(self) -> ArchiveRuntimeReadiness:
        return ArchiveRuntimeReadiness(
            repository_ready=dependency_is_ready(self.repository.check_ready),
            storage_ready=dependency_is_ready(self.storage.check_ready),
            access_audit_ready=dependency_is_ready(self.audit_repository.check_ready),
        )

    def close(self) -> None:
        """Release composed resources - today the shared PostgreSQL pool - at app shutdown."""
        for release in self._on_close:
            release()

    def get_lifecycle_posture(self, document_id: str) -> ArchiveDocumentMetadata:
        metadata = self._refresh_legal_hold_summary(self._get_existing_metadata(document_id))
        metadata, _, _ = self._evaluate_purge(metadata, date.today())
        return metadata

    @archive_metric("archive_create")
    def create_document(
        self,
        *,
        command: ArchiveDocumentCreateCommand,
        caller_context: CallerContext,
        trace_id: str,
    ) -> ArchiveDocumentMetadata:
        self.authorization_policy.authorize(
            permission=ArchivePermission.CREATE_DOCUMENT,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
        )
        content = self._decode_content(command.content_base64)
        metadata = self.writer.archive_document(metadata_input=command.metadata, content=content)
        self._record_allowed(
            event_type=AccessEventType.ARCHIVE_CREATE,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=metadata.document_id,
        )
        return metadata

    @archive_metric("metadata_lookup")
    def get_document_metadata(
        self,
        *,
        document_id: str,
        caller_context: CallerContext,
        trace_id: str,
    ) -> ArchiveDocumentMetadata:
        metadata = self._get_authorized_document_metadata(
            document_id=document_id,
            permission=ArchivePermission.READ_METADATA,
            caller_context=caller_context,
            trace_id=trace_id,
        )
        self._record_allowed(
            event_type=AccessEventType.METADATA_READ,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
        )
        return metadata

    @archive_metric("metadata_lookup")
    def get_document_metadata_by_request_id(
        self,
        *,
        archive_request_id: str,
        caller_context: CallerContext,
        trace_id: str,
    ) -> ArchiveDocumentMetadata:
        """Ambiguity-resolution read: after a lost ingest response, answers
        whether the idempotent request committed so recovery can adopt the
        existing document (lotus-report#211). Authorization and audit run
        through the standard metadata read; unknown ids answer identically.
        """

        record = self.repository.get_by_archive_request_id(archive_request_id)
        if record is None:
            raise DocumentNotFoundError("document_not_found")
        return self.get_document_metadata(
            document_id=record.document_id,
            caller_context=caller_context,
            trace_id=trace_id,
        )

    @archive_metric("binary_download")
    def get_document_binary(
        self,
        *,
        document_id: str,
        caller_context: CallerContext,
        trace_id: str,
    ) -> tuple[ArchiveDocumentMetadata, bytes]:
        metadata = self._get_authorized_document_metadata(
            document_id=document_id,
            permission=ArchivePermission.DOWNLOAD_BINARY,
            caller_context=caller_context,
            trace_id=trace_id,
        )
        try:
            content = self.storage.get(key=metadata.storage_key)
        except StorageReadFailedError:
            self._record_allowed(
                event_type=AccessEventType.BINARY_DOWNLOAD,
                caller_context=caller_context,
                trace_id=trace_id,
                document_id=document_id,
                operation_reason_code="document_binary_missing",
            )
            raise
        if calculate_checksum(content, algorithm=metadata.checksum_algorithm) != metadata.checksum:
            self._record_allowed(
                event_type=AccessEventType.BINARY_DOWNLOAD,
                caller_context=caller_context,
                trace_id=trace_id,
                document_id=document_id,
                operation_reason_code="document_checksum_mismatch",
            )
            raise DocumentChecksumMismatchError("archived document checksum mismatch")
        self._record_allowed(
            event_type=AccessEventType.BINARY_DOWNLOAD,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
            operation_reason_code="download_succeeded",
        )
        return metadata, content

    @archive_metric("access_events_lookup")
    def list_access_events(
        self,
        *,
        document_id: str,
        caller_context: CallerContext,
        trace_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[AccessAuditEvent], int]:
        self.authorization_policy.authorize(
            permission=ArchivePermission.READ_ACCESS_EVENTS,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
            document_id=document_id,
        )
        self._get_existing_metadata(document_id)
        self._record_allowed(
            event_type=AccessEventType.ACCESS_EVENTS_READ,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
        )
        events = self.audit_repository.list_by_document_id(document_id, limit=limit, offset=offset)
        total = self.audit_repository.count_by_document_id(document_id)
        return events, total

    @archive_metric("retention_lookup")
    def get_retention(
        self,
        *,
        document_id: str,
        caller_context: CallerContext,
        trace_id: str,
    ) -> ArchiveDocumentMetadata:
        self.authorization_policy.authorize(
            permission=ArchivePermission.READ_RETENTION,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
            document_id=document_id,
        )
        metadata = self._refresh_legal_hold_summary(self._get_existing_metadata(document_id))
        self._record_allowed(
            event_type=AccessEventType.RETENTION_READ,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
        )
        return metadata

    @archive_metric("purge_evaluation")
    def evaluate_purge(
        self,
        *,
        document_id: str,
        caller_context: CallerContext,
        trace_id: str,
        evaluation_date: date | None = None,
    ) -> tuple[ArchiveDocumentMetadata, bool, str]:
        self.authorization_policy.authorize(
            permission=ArchivePermission.EVALUATE_PURGE,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
            document_id=document_id,
        )
        metadata = self._refresh_legal_hold_summary(self._get_existing_metadata(document_id))
        metadata, purge_eligible, reason_code = self._evaluate_purge(metadata, evaluation_date)
        self._record_allowed(
            event_type=AccessEventType.PURGE_EVALUATION,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
        )
        return metadata, purge_eligible, reason_code

    @archive_metric("purge_execution")
    def purge_document(
        self,
        *,
        document_id: str,
        caller_context: CallerContext,
        trace_id: str,
        evaluation_date: date | None = None,
    ) -> tuple[ArchiveDocumentMetadata, str]:
        self.authorization_policy.authorize(
            permission=ArchivePermission.EXECUTE_PURGE,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
            document_id=document_id,
        )
        metadata = self._refresh_legal_hold_summary(self._get_existing_metadata(document_id))
        if metadata.purge_status is PurgeStatus.PURGED:
            self._record_allowed(
                event_type=AccessEventType.PURGE_EXECUTION,
                caller_context=caller_context,
                trace_id=trace_id,
                document_id=document_id,
                operation_reason_code="already_purged",
            )
            return metadata, "already_purged"
        metadata, purge_eligible, reason_code = self._evaluate_purge(metadata, evaluation_date)
        if not purge_eligible:
            self._record_allowed(
                event_type=AccessEventType.PURGE_EXECUTION,
                caller_context=caller_context,
                trace_id=trace_id,
                document_id=document_id,
                operation_reason_code=reason_code,
            )
            if reason_code == "legal_hold_active":
                raise LegalHoldActiveError("legal hold blocks purge")
            raise PurgeNotEligibleError("document is not purge eligible")

        # The intent is recorded before the object is deleted, because deletion
        # is irreversible and the record is not. If this claim fails, nothing has
        # been destroyed. If the delete or the save below fails, the record
        # already says destruction was started, which is what lets a retry
        # finish and stops a reader believing the document is still retained.
        #
        # Claimed conditionally rather than read-then-saved: the previous form
        # decided on a snapshot and wrote it back wholesale, so a legal hold
        # admitted in between was erased along with the purge state it had
        # already committed. The condition and the write are now one step, and
        # a hold that won the race makes this return None.
        started_at = datetime.now(timezone.utc)
        claimed = self.repository.begin_purge(document_id=document_id, started_at=started_at)
        if claimed is None:
            self._record_allowed(
                event_type=AccessEventType.PURGE_EXECUTION,
                caller_context=caller_context,
                trace_id=trace_id,
                document_id=document_id,
                operation_reason_code="legal_hold_active",
            )
            raise LegalHoldActiveError("legal hold blocks purge")
        metadata = claimed
        self.storage.delete(key=metadata.storage_key)
        # Recorded against the stored row rather than by saving back the
        # snapshot read before the delete. That snapshot carried every
        # mutable column, so writing it wholesale reverted whatever another
        # writer had committed meanwhile -- the same defect as above, on the
        # path where the bytes are already gone and the record is all that
        # is left to be wrong.
        completed = self.repository.complete_purge(
            document_id=document_id,
            purged_at=datetime.now(timezone.utc),
        )
        metadata = completed if completed is not None else metadata
        self._record_allowed(
            event_type=AccessEventType.PURGE_EXECUTION,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
            operation_reason_code="purged",
        )
        return metadata, "purged"

    @archive_metric("legal_hold_set")
    def set_legal_hold(
        self,
        *,
        document_id: str,
        command: LegalHoldCreateCommand,
        caller_context: CallerContext,
        trace_id: str,
    ) -> LegalHoldRecord:
        self.authorization_policy.authorize(
            permission=ArchivePermission.MANAGE_LEGAL_HOLD,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
            document_id=document_id,
        )
        self._get_existing_metadata(document_id)
        for existing in self.repository.list_legal_holds(document_id):
            if (
                existing.hold_status is LegalHoldStatus.ACTIVE
                and existing.authority_reference == command.authority_reference
                and existing.hold_reason == command.hold_reason
            ):
                # A retry of an identical request converges on the hold it already
                # created. Minting a second hold here would leave a duplicate the
                # caller never saw an id for, blocking purge after they release
                # the one they know about.
                self._record_allowed(
                    event_type=AccessEventType.LEGAL_HOLD_SET,
                    caller_context=caller_context,
                    trace_id=trace_id,
                    document_id=document_id,
                    operation_reason_code="legal_hold_already_active",
                )
                return existing
        # Claim the document for preservation before any hold record exists.
        # Refusal precedes every effect: on refusal no hold is written, and the
        # denial is audited. A hold cannot preserve an object whose deletion has
        # already been ordered, and recording one would leave the document
        # asserting a preservation that is not true.
        legal_hold = LegalHoldRecord(
            legal_hold_id=f"hold_{uuid4().hex}",
            document_id=document_id,
            hold_reason=command.hold_reason,
            authority_reference=command.authority_reference,
            requested_by=caller_context.actor_id,
        )
        # Admission, the hold row and the summary commit together. As three
        # steps there was a window after admission and before the row
        # existed in which a competing purge recounted active holds, found
        # none, wrote `clear` and deleted the object -- after which this
        # hold landed and returned success. The observed end state was
        # PURGED metadata, one ACTIVE hold and absent bytes.
        admitted = self.repository.admit_and_record_legal_hold(
            document_id=document_id,
            legal_hold=legal_hold,
        )
        if admitted is None:
            self._record_allowed(
                event_type=AccessEventType.LEGAL_HOLD_SET,
                caller_context=caller_context,
                trace_id=trace_id,
                document_id=document_id,
                operation_reason_code="purge_already_started",
            )
            raise PurgeAlreadyStartedError(
                "destruction has already been started for this document; "
                "a legal hold cannot preserve it"
            )
        self._record_allowed(
            event_type=AccessEventType.LEGAL_HOLD_SET,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
        )
        return legal_hold

    @archive_metric("legal_hold_release")
    def release_legal_hold(
        self,
        *,
        document_id: str,
        legal_hold_id: str,
        release_reason: str,
        caller_context: CallerContext,
        trace_id: str,
    ) -> LegalHoldRecord:
        self.authorization_policy.authorize(
            permission=ArchivePermission.MANAGE_LEGAL_HOLD,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
            document_id=document_id,
        )
        self._get_existing_metadata(document_id)
        legal_hold = self.repository.get_legal_hold(legal_hold_id)
        if legal_hold is None or legal_hold.document_id != document_id:
            raise LegalHoldNotFoundError("legal hold was not found")
        if legal_hold.hold_status is LegalHoldStatus.ACTIVE:
            legal_hold = legal_hold.model_copy(
                update={
                    "hold_status": LegalHoldStatus.CLEAR,
                    "released_by": caller_context.actor_id,
                    "released_at": datetime.now(timezone.utc),
                    "release_reason": release_reason,
                }
            )
            legal_hold = self.repository.save_legal_hold(legal_hold)
        self._refresh_legal_hold_summary(self._get_existing_metadata(document_id))
        self._record_allowed(
            event_type=AccessEventType.LEGAL_HOLD_RELEASE,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
        )
        return legal_hold

    @archive_metric("current_document_lookup")
    def get_current_document_metadata(
        self,
        *,
        document_id: str,
        caller_context: CallerContext,
        trace_id: str,
    ) -> ArchiveDocumentMetadata:
        metadata = self._get_authorized_document_metadata(
            document_id=document_id,
            permission=ArchivePermission.READ_METADATA,
            caller_context=caller_context,
            trace_id=trace_id,
        )
        current = self._resolve_current_document(metadata)
        self._record_allowed(
            event_type=AccessEventType.CURRENT_DOCUMENT_READ,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
        )
        return current

    @archive_metric("batch_access_preflight")
    def preflight_document_access(
        self,
        *,
        document_ids: tuple[str, ...],
        caller_context: CallerContext,
        trace_id: str,
    ) -> ArchiveAccessPreflightResult:
        if not document_ids:
            raise MetadataValidationError("access preflight requires at least one document id")
        if len(document_ids) > MAX_PREFLIGHT_DOCUMENT_IDS:
            raise MetadataValidationError(
                "access preflight accepts at most "
                f"{MAX_PREFLIGHT_DOCUMENT_IDS} document ids per request"
            )
        self.authorization_policy.authorize(
            permission=ArchivePermission.READ_BATCH_ACCESS_PREFLIGHT,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
        )
        require_caller_scope(caller_context)

        try:
            lookup = self.repository.get_by_document_ids(document_ids)
        except ArchiveDocumentLookupUnavailableError:
            items = tuple(
                ArchiveAccessPreflightItem(
                    document_id=document_id,
                    state=ArchiveAccessState.UNAVAILABLE,
                    reason_code=ArchiveAccessReasonCode.LOOKUP_UNAVAILABLE,
                )
                for document_id in document_ids
            )
            result = ArchiveAccessPreflightResult(
                items=items,
                result_state=ArchiveAccessResultState.UNAVAILABLE,
            )
            self._record_preflight_audit(
                items=items,
                audit_reasons=tuple(item.reason_code for item in items),
                caller_context=caller_context,
                trace_id=trace_id,
            )
            return result

        evaluated = tuple(
            preflight_item(
                document_id=document_id,
                metadata=lookup.documents.get(document_id),
                unavailable=document_id in lookup.unavailable_document_ids,
                caller_context=caller_context,
                authorization_policy=self.authorization_policy,
            )
            for document_id in document_ids
        )
        items = tuple(item for item, _ in evaluated)
        audit_reasons = tuple(reason for _, reason in evaluated)
        result = ArchiveAccessPreflightResult(
            items=items,
            result_state=result_state_for_items(items),
        )
        self._record_preflight_audit(
            items=items,
            audit_reasons=audit_reasons,
            caller_context=caller_context,
            trace_id=trace_id,
        )
        return result

    @archive_metric("metadata_lookup")
    def list_document_source_events(
        self,
        *,
        document_id: str,
        caller_context: CallerContext,
        trace_id: str,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[ArchiveDocumentMetadata, ArchiveDocumentMetadata, list[dict[str, object]]]:
        self.authorization_policy.authorize(
            permission=ArchivePermission.READ_METADATA,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
            document_id=document_id,
        )
        metadata = self._get_existing_metadata(document_id)
        current = self._resolve_current_document(metadata)
        relationships = self.repository.list_lifecycle_relationships(document_id)
        events = build_archive_document_source_events(
            metadata=metadata,
            current_document_id=current.document_id,
            lifecycle_relationships=relationships,
        )
        self._record_allowed(
            event_type=AccessEventType.SOURCE_EVENTS_READ,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
        )
        return metadata, current, events

    @archive_metric("lifecycle_supersede")
    def supersede_document(
        self,
        *,
        document_id: str,
        command: LifecycleTransitionCommand,
        caller_context: CallerContext,
        trace_id: str,
    ) -> tuple[LifecycleRelationshipRecord, ArchiveDocumentMetadata]:
        return self._apply_lifecycle_transition(
            source_document_id=document_id,
            command=command,
            transition_type=LifecycleTransitionType.SUPERSEDE,
            event_type=AccessEventType.LIFECYCLE_SUPERSEDE,
            caller_context=caller_context,
            trace_id=trace_id,
        )

    @archive_metric("lifecycle_correct")
    def correct_document(
        self,
        *,
        document_id: str,
        command: LifecycleTransitionCommand,
        caller_context: CallerContext,
        trace_id: str,
    ) -> tuple[LifecycleRelationshipRecord, ArchiveDocumentMetadata]:
        return self._apply_lifecycle_transition(
            source_document_id=document_id,
            command=command,
            transition_type=LifecycleTransitionType.CORRECT,
            event_type=AccessEventType.LIFECYCLE_CORRECT,
            caller_context=caller_context,
            trace_id=trace_id,
        )

    @archive_metric("lifecycle_reissue")
    def reissue_document(
        self,
        *,
        document_id: str,
        command: LifecycleTransitionCommand,
        caller_context: CallerContext,
        trace_id: str,
    ) -> tuple[LifecycleRelationshipRecord, ArchiveDocumentMetadata]:
        return self._apply_lifecycle_transition(
            source_document_id=document_id,
            command=command,
            transition_type=LifecycleTransitionType.REISSUE,
            event_type=AccessEventType.LIFECYCLE_REISSUE,
            caller_context=caller_context,
            trace_id=trace_id,
        )

    def _get_existing_metadata(self, document_id: str) -> ArchiveDocumentMetadata:
        metadata = self.repository.get_by_document_id(document_id)
        if metadata is None:
            raise DocumentNotFoundError("archive document was not found")
        return metadata

    def _get_authorized_document_metadata(
        self,
        *,
        document_id: str,
        permission: ArchivePermission,
        caller_context: CallerContext,
        trace_id: str,
    ) -> ArchiveDocumentMetadata:
        self.authorization_policy.authorize(
            permission=permission,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
            document_id=document_id,
        )
        metadata = self._get_existing_metadata(document_id)
        self.authorization_policy.authorize_document_scope(
            metadata=metadata,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
        )
        return metadata

    def _record_preflight_audit(
        self,
        *,
        items: tuple[ArchiveAccessPreflightItem, ...],
        audit_reasons: tuple[ArchiveAccessReasonCode, ...],
        caller_context: CallerContext,
        trace_id: str,
    ) -> None:
        """Record the granular reason per item, not the collapsed response reason.

        The response deliberately hides whether a denied id exists (issue #88); the audit is
        where an investigator distinguishes document_not_found from caller_scope_mismatch.
        """
        for item, audit_reason in zip(items, audit_reasons, strict=True):
            self.audit_repository.record(
                access_audit_event(
                    event_type=AccessEventType.BATCH_ACCESS_PREFLIGHT,
                    caller_context=caller_context,
                    trace_id=trace_id,
                    authorization_decision=(
                        AuthorizationDecision.ALLOWED
                        if item.state is ArchiveAccessState.ALLOWED
                        else AuthorizationDecision.DENIED
                    ),
                    authorization_reason_code=audit_reason.value,
                    operation_reason_code=audit_reason.value,
                    document_id=item.document_id,
                )
            )

    def _apply_lifecycle_transition(
        self,
        *,
        source_document_id: str,
        command: LifecycleTransitionCommand,
        transition_type: LifecycleTransitionType,
        event_type: AccessEventType,
        caller_context: CallerContext,
        trace_id: str,
    ) -> tuple[LifecycleRelationshipRecord, ArchiveDocumentMetadata]:
        self.authorization_policy.authorize(
            permission=ArchivePermission.MANAGE_LIFECYCLE,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
            document_id=source_document_id,
        )
        source = self._get_existing_metadata(source_document_id)
        target = self._get_existing_metadata(command.target_document_id)
        already_applied = self._find_applied_transition(
            source=source,
            target=target,
            transition_type=transition_type,
        )
        if already_applied is not None:
            self._record_allowed(
                event_type=event_type,
                caller_context=caller_context,
                trace_id=trace_id,
                document_id=source.document_id,
                operation_reason_code="lifecycle_transition_already_recorded",
            )
            return already_applied, self._resolve_current_document(target)
        self._validate_lifecycle_transition(
            source=source,
            target=target,
            transition_type=transition_type,
        )

        now = datetime.now(timezone.utc)
        source = source.model_copy(
            update={
                "superseded_by_document_id": target.document_id,
                "updated_at": now,
            }
        )
        # _validate_lifecycle_transition already rejected any type outside the mapping.
        origin_field = LIFECYCLE_TARGET_ORIGIN_FIELD[transition_type]
        target = target.model_copy(update={"updated_at": now, origin_field: source.document_id})
        relationship = LifecycleRelationshipRecord(
            lifecycle_relationship_id=f"life_{uuid4().hex}",
            source_document_id=source.document_id,
            target_document_id=target.document_id,
            transition_type=transition_type,
            transition_reason=command.transition_reason,
            transition_reason_code=LIFECYCLE_TRANSITION_REASON_CODES[transition_type],
            requested_by=caller_context.actor_id,
        )

        # One atomic unit in the repository: a crash between these writes would leave a
        # half-linked chain that the validation guards make unrepairable through the API.
        # The previous service-level compensation could not survive a process crash and
        # failed for the same reasons the forward writes did.
        saved_relationship = self.repository.apply_lifecycle_transition(
            source, target, relationship
        )
        self._record_allowed(
            event_type=event_type,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=source.document_id,
            operation_reason_code="lifecycle_transition_recorded",
        )
        return saved_relationship, self._resolve_current_document(target)

    def _find_applied_transition(
        self,
        *,
        source: ArchiveDocumentMetadata,
        target: ArchiveDocumentMetadata,
        transition_type: LifecycleTransitionType,
    ) -> LifecycleRelationshipRecord | None:
        """The recorded relationship when exactly this transition already holds, else None.

        A retry is recognized only when the whole chain agrees: the source points at this
        target, the target carries this transition's origin field back at the source, and
        the relationship record exists. Anything less is a genuine conflict and falls
        through to the validation guards.
        """
        origin_field = LIFECYCLE_TARGET_ORIGIN_FIELD.get(transition_type)
        if origin_field is None:
            return None
        if source.superseded_by_document_id != target.document_id:
            return None
        if getattr(target, origin_field) != source.document_id:
            return None
        for relationship in self.repository.list_lifecycle_relationships(source.document_id):
            if (
                relationship.source_document_id == source.document_id
                and relationship.target_document_id == target.document_id
                and relationship.transition_type is transition_type
            ):
                return relationship
        return None

    def _validate_lifecycle_transition(
        self,
        *,
        source: ArchiveDocumentMetadata,
        target: ArchiveDocumentMetadata,
        transition_type: LifecycleTransitionType,
    ) -> None:
        if source.document_id == target.document_id:
            raise UnsupportedLifecycleTransitionError("document cannot transition to itself")
        if source.purge_status is PurgeStatus.PURGED or target.purge_status is PurgeStatus.PURGED:
            raise UnsupportedLifecycleTransitionError("purged documents cannot transition")
        if source.superseded_by_document_id is not None:
            raise SupersessionConflictError("source document is already historical")
        if target.superseded_by_document_id is not None:
            raise SupersessionConflictError("target document is already historical")
        existing_origin = (
            target.supersedes_document_id
            or target.correction_of_document_id
            or target.reissue_of_document_id
        )
        if existing_origin is not None:
            raise SupersessionConflictError("target document already has a lifecycle origin")
        if transition_type not in LIFECYCLE_TARGET_ORIGIN_FIELD:
            raise UnsupportedLifecycleTransitionError("unsupported lifecycle transition")

    def _resolve_current_document(
        self,
        metadata: ArchiveDocumentMetadata,
    ) -> ArchiveDocumentMetadata:
        visited_document_ids = {metadata.document_id}
        current = metadata
        while current.superseded_by_document_id is not None:
            if current.superseded_by_document_id in visited_document_ids:
                raise SupersessionConflictError("document lifecycle relationship cycle detected")
            visited_document_ids.add(current.superseded_by_document_id)
            current = self._get_existing_metadata(current.superseded_by_document_id)
        return current

    def _evaluate_purge(
        self,
        metadata: ArchiveDocumentMetadata,
        evaluation_date: date | None,
    ) -> tuple[ArchiveDocumentMetadata, bool, str]:
        """Delegated to `purge_transitions`, which owns how a decision is committed."""
        return evaluate_purge(self.repository, metadata, evaluation_date)

    def _refresh_legal_hold_summary(
        self,
        metadata: ArchiveDocumentMetadata,
    ) -> ArchiveDocumentMetadata:
        """Recount active holds and write ONLY those two columns.

        The caller's `metadata` is used for its document id and for deciding
        whether anything changed. It is never written back: the repository
        updates the hold columns against the stored row, so this method cannot
        revert a `purge_status`, `purge_started_at` or `purged_at` committed by
        another writer since the caller's read. That reversion is exactly how a
        concurrent hold used to erase a completed purge and leave the record
        asserting preservation over deleted bytes.
        """
        active_holds = [
            hold
            for hold in self.repository.list_legal_holds(metadata.document_id)
            if hold.hold_status is LegalHoldStatus.ACTIVE
        ]
        legal_hold_status = LegalHoldStatus.ACTIVE if active_holds else LegalHoldStatus.CLEAR
        if (
            metadata.legal_hold_count == len(active_holds)
            and metadata.legal_hold_status is legal_hold_status
        ):
            return metadata
        updated = self.repository.update_legal_hold_summary(
            document_id=metadata.document_id,
            legal_hold_status=legal_hold_status,
            legal_hold_count=len(active_holds),
        )
        return updated if updated is not None else metadata

    def _record_allowed(
        self,
        *,
        event_type: AccessEventType,
        caller_context: CallerContext,
        trace_id: str,
        document_id: str,
        operation_reason_code: str | None = None,
    ) -> None:
        self.audit_repository.record(
            access_audit_event(
                event_type=event_type,
                caller_context=caller_context,
                trace_id=trace_id,
                authorization_decision=AuthorizationDecision.ALLOWED,
                authorization_reason_code="allowed",
                document_id=document_id,
                operation_reason_code=operation_reason_code,
            )
        )

    def _decode_content(self, content_base64: str) -> bytes:
        try:
            content = b64decode(content_base64, validate=True)
        except Base64DecodeError as exc:
            raise MetadataValidationError("document content must be valid base64") from exc
        if len(content) > self.max_decoded_document_bytes:
            raise MetadataValidationError("document content exceeds configured archive size limit")
        return content
