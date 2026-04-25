from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64DecodeError
from datetime import date, datetime, timezone
from uuid import uuid4

from app.archive.api_models import ArchiveDocumentCreateRequest, LegalHoldCreateRequest
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
)
from app.archive.models import (
    ArchiveDocumentMetadata,
    LegalHoldRecord,
    LegalHoldStatus,
    PurgeStatus,
)
from app.archive.repository import ArchiveDocumentRepository
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

    def _get_existing_metadata(self, document_id: str) -> ArchiveDocumentMetadata:
        metadata = self.repository.get_by_document_id(document_id)
        if metadata is None:
            raise DocumentNotFoundError("archive document was not found")
        return metadata

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
