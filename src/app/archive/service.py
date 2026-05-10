from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64DecodeError
from datetime import date, datetime, timezone
from uuid import uuid4

from app.archive.api_models import (
    ArchiveDocumentCreateRequest,
    LegalHoldCreateRequest,
    LifecycleTransitionRequest,
)
from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import (
    AccessAuditEvent,
    AccessAuditRepository,
    AccessEventType,
    AuthorizationDecision,
    access_audit_event,
)
from app.archive.authorization import ArchiveAuthorizationPolicy, ArchivePermission
from app.archive.checksum import calculate_checksum
from app.archive.exceptions import (
    DocumentChecksumMismatchError,
    DocumentNotFoundError,
    LegalHoldActiveError,
    LegalHoldNotFoundError,
    MetadataValidationError,
    PurgeNotEligibleError,
    SupersessionConflictError,
    UnsupportedLifecycleTransitionError,
)
from app.archive.metrics import archive_metric
from app.archive.models import (
    ArchiveDocumentMetadata,
    LegalHoldRecord,
    LegalHoldStatus,
    LifecycleRelationshipRecord,
    LifecycleTransitionType,
    PurgeStatus,
)
from app.archive.repository import ArchiveDocumentRepository
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
    ) -> None:
        self.writer = writer
        self.repository = repository
        self.storage = storage
        self.audit_repository = audit_repository
        self.authorization_policy = authorization_policy or ArchiveAuthorizationPolicy()

    @archive_metric("archive_create")
    def create_document(
        self,
        *,
        request: ArchiveDocumentCreateRequest,
        caller_context: CallerContext,
        trace_id: str,
    ) -> ArchiveDocumentMetadata:
        self.authorization_policy.authorize(
            permission=ArchivePermission.CREATE_DOCUMENT,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
        )
        content = self._decode_content(request.content_base64)
        metadata = self.writer.archive_document(metadata_input=request.metadata, content=content)
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
        self.authorization_policy.authorize(
            permission=ArchivePermission.READ_METADATA,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
            document_id=document_id,
        )
        metadata = self._get_existing_metadata(document_id)
        self._record_allowed(
            event_type=AccessEventType.METADATA_READ,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
        )
        return metadata

    @archive_metric("binary_download")
    def get_document_binary(
        self,
        *,
        document_id: str,
        caller_context: CallerContext,
        trace_id: str,
    ) -> tuple[ArchiveDocumentMetadata, bytes]:
        self.authorization_policy.authorize(
            permission=ArchivePermission.DOWNLOAD_BINARY,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
            document_id=document_id,
        )
        metadata = self._get_existing_metadata(document_id)
        content = self.storage.get(key=metadata.storage_key)
        if calculate_checksum(content, algorithm=metadata.checksum_algorithm) != metadata.checksum:
            raise DocumentChecksumMismatchError("archived document checksum mismatch")
        self._record_allowed(
            event_type=AccessEventType.BINARY_DOWNLOAD,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
        )
        return metadata, content

    @archive_metric("access_events_lookup")
    def list_access_events(
        self,
        *,
        document_id: str,
        caller_context: CallerContext,
        trace_id: str,
    ) -> list[AccessAuditEvent]:
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
        return self.audit_repository.list_by_document_id(document_id)

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
            )
            return metadata, "already_purged"
        metadata, purge_eligible, reason_code = self._evaluate_purge(metadata, evaluation_date)
        if not purge_eligible:
            if reason_code == "legal_hold_active":
                raise LegalHoldActiveError("legal hold blocks purge")
            raise PurgeNotEligibleError("document is not purge eligible")

        self.storage.delete(key=metadata.storage_key)
        now = datetime.now(timezone.utc)
        metadata = metadata.model_copy(
            update={
                "purge_status": PurgeStatus.PURGED,
                "purged_at": now,
                "updated_at": now,
            }
        )
        metadata = self.repository.save(metadata)
        self._record_allowed(
            event_type=AccessEventType.PURGE_EXECUTION,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
        )
        return metadata, "purged"

    @archive_metric("legal_hold_set")
    def set_legal_hold(
        self,
        *,
        document_id: str,
        request: LegalHoldCreateRequest,
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
        metadata = self._get_existing_metadata(document_id)
        legal_hold = LegalHoldRecord(
            legal_hold_id=f"hold_{uuid4().hex}",
            document_id=document_id,
            hold_reason=request.hold_reason,
            authority_reference=request.authority_reference,
            requested_by=caller_context.actor_id,
        )
        legal_hold = self.repository.save_legal_hold(legal_hold)
        self._refresh_legal_hold_summary(metadata)
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
        self.authorization_policy.authorize(
            permission=ArchivePermission.READ_METADATA,
            caller_context=caller_context,
            audit_repository=self.audit_repository,
            trace_id=trace_id,
            document_id=document_id,
        )
        current = self._resolve_current_document(self._get_existing_metadata(document_id))
        self._record_allowed(
            event_type=AccessEventType.CURRENT_DOCUMENT_READ,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=document_id,
        )
        return current

    @archive_metric("metadata_lookup")
    def list_document_source_events(
        self,
        *,
        document_id: str,
        caller_context: CallerContext,
        trace_id: str,
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
        request: LifecycleTransitionRequest,
        caller_context: CallerContext,
        trace_id: str,
    ) -> tuple[LifecycleRelationshipRecord, ArchiveDocumentMetadata]:
        return self._apply_lifecycle_transition(
            source_document_id=document_id,
            request=request,
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
        request: LifecycleTransitionRequest,
        caller_context: CallerContext,
        trace_id: str,
    ) -> tuple[LifecycleRelationshipRecord, ArchiveDocumentMetadata]:
        return self._apply_lifecycle_transition(
            source_document_id=document_id,
            request=request,
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
        request: LifecycleTransitionRequest,
        caller_context: CallerContext,
        trace_id: str,
    ) -> tuple[LifecycleRelationshipRecord, ArchiveDocumentMetadata]:
        return self._apply_lifecycle_transition(
            source_document_id=document_id,
            request=request,
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

    def _apply_lifecycle_transition(
        self,
        *,
        source_document_id: str,
        request: LifecycleTransitionRequest,
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
        target = self._get_existing_metadata(request.target_document_id)
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
        target_updates: dict[str, object] = {"updated_at": now}
        if transition_type is LifecycleTransitionType.SUPERSEDE:
            target_updates["supersedes_document_id"] = source.document_id
        elif transition_type is LifecycleTransitionType.CORRECT:
            target_updates["correction_of_document_id"] = source.document_id
        elif transition_type is LifecycleTransitionType.REISSUE:
            target_updates["reissue_of_document_id"] = source.document_id
        else:
            raise UnsupportedLifecycleTransitionError("unsupported lifecycle transition")

        target = target.model_copy(update=target_updates)
        relationship = LifecycleRelationshipRecord(
            lifecycle_relationship_id=f"life_{uuid4().hex}",
            source_document_id=source.document_id,
            target_document_id=target.document_id,
            transition_type=transition_type,
            transition_reason=request.transition_reason,
            requested_by=caller_context.actor_id,
        )

        self.repository.save(source)
        target = self.repository.save(target)
        relationship = self.repository.save_lifecycle_relationship(relationship)
        self._record_allowed(
            event_type=event_type,
            caller_context=caller_context,
            trace_id=trace_id,
            document_id=source.document_id,
        )
        return relationship, self._resolve_current_document(target)

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
        if transition_type not in {
            LifecycleTransitionType.SUPERSEDE,
            LifecycleTransitionType.CORRECT,
            LifecycleTransitionType.REISSUE,
        }:
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
        if metadata.purge_status is PurgeStatus.PURGED:
            return metadata, True, "already_purged"
        if metadata.legal_hold_status is LegalHoldStatus.ACTIVE:
            metadata = self._update_purge_status(metadata, PurgeStatus.NOT_ELIGIBLE)
            return metadata, False, "legal_hold_active"
        if metadata.retain_until_date is None:
            metadata = self._update_purge_status(metadata, PurgeStatus.NOT_ELIGIBLE)
            return metadata, False, "retain_until_date_missing"
        effective_date = evaluation_date or date.today()
        if metadata.retain_until_date > effective_date:
            metadata = self._update_purge_status(metadata, PurgeStatus.NOT_ELIGIBLE)
            return metadata, False, "retention_period_active"
        now = datetime.now(timezone.utc)
        metadata = metadata.model_copy(
            update={
                "purge_status": PurgeStatus.ELIGIBLE,
                "purge_eligible_at": metadata.purge_eligible_at or now,
                "updated_at": now,
            }
        )
        return self.repository.save(metadata), True, "retention_elapsed"

    def _update_purge_status(
        self,
        metadata: ArchiveDocumentMetadata,
        purge_status: PurgeStatus,
    ) -> ArchiveDocumentMetadata:
        if metadata.purge_status is purge_status:
            return metadata
        return self.repository.save(
            metadata.model_copy(
                update={
                    "purge_status": purge_status,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
        )

    def _refresh_legal_hold_summary(
        self,
        metadata: ArchiveDocumentMetadata,
    ) -> ArchiveDocumentMetadata:
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
        return self.repository.save(
            metadata.model_copy(
                update={
                    "legal_hold_count": len(active_holds),
                    "legal_hold_status": legal_hold_status,
                    "updated_at": datetime.now(timezone.utc),
                }
            )
        )

    def _record_allowed(
        self,
        *,
        event_type: AccessEventType,
        caller_context: CallerContext,
        trace_id: str,
        document_id: str,
    ) -> None:
        self.audit_repository.record(
            access_audit_event(
                event_type=event_type,
                caller_context=caller_context,
                trace_id=trace_id,
                authorization_decision=AuthorizationDecision.ALLOWED,
                authorization_reason_code="allowed",
                document_id=document_id,
            )
        )

    def _decode_content(self, content_base64: str) -> bytes:
        try:
            return b64decode(content_base64, validate=True)
        except Base64DecodeError as exc:
            raise MetadataValidationError("document content must be valid base64") from exc
