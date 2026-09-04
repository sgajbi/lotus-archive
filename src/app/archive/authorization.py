from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.archive.audit import (
    AccessAuditRepository,
    AccessEventType,
    AuthorizationDecision,
    access_audit_event,
)
from app.archive.access_preflight import (
    ArchiveAccessDecision,
    ArchiveAccessReasonCode,
    ArchiveAccessState,
)
from app.archive.models import ArchiveDocumentMetadata, PurgeStatus
from app.security.caller_context import CallerContext, CallerScopeMissingError


class ArchivePermission(StrEnum):
    CREATE_DOCUMENT = "create_document"
    READ_METADATA = "read_metadata"
    DOWNLOAD_BINARY = "download_binary"
    READ_ACCESS_EVENTS = "read_access_events"
    READ_RETENTION = "read_retention"
    EVALUATE_PURGE = "evaluate_purge"
    EXECUTE_PURGE = "execute_purge"
    MANAGE_LEGAL_HOLD = "manage_legal_hold"
    MANAGE_LIFECYCLE = "manage_lifecycle"
    READ_IDEA_LIFECYCLE_DECISION = "read_idea_lifecycle_decision"
    READ_BATCH_ACCESS_PREFLIGHT = "read_batch_access_preflight"


class AuthorizationFailedError(PermissionError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class ArchiveAuthorizationPolicy:
    #: The render#120 cutover is complete: lotus-render is the ONE archive
    #: transmit authority for governed documents. lotus-report's byte relay
    #: retired (its PR #267); this revocation is the ratchet that makes the
    #: single delivery path an enforced fact rather than a convention.
    create_callers: frozenset[str] = frozenset({"lotus-render"})
    read_callers: frozenset[str] = frozenset({"lotus-report", "lotus-gateway"})
    audit_callers: frozenset[str] = frozenset({"lotus-report"})
    retention_callers: frozenset[str] = frozenset({"lotus-report"})
    purge_callers: frozenset[str] = frozenset({"lotus-report"})
    legal_hold_callers: frozenset[str] = frozenset({"lotus-report"})
    lifecycle_callers: frozenset[str] = frozenset({"lotus-report"})
    idea_lifecycle_decision_callers: frozenset[str] = frozenset({"lotus-idea", "lotus-report"})
    batch_access_preflight_callers: frozenset[str] = frozenset({"lotus-gateway"})

    def authorize(
        self,
        *,
        permission: ArchivePermission,
        caller_context: CallerContext,
        audit_repository: AccessAuditRepository,
        trace_id: str,
        document_id: str | None = None,
    ) -> None:
        allowed_callers = self._allowed_callers_for(permission)
        if caller_context.caller_service in allowed_callers:
            return

        audit_repository.record(
            access_audit_event(
                event_type=AccessEventType.AUTHORIZATION_DENIED,
                caller_context=caller_context,
                trace_id=trace_id,
                authorization_decision=AuthorizationDecision.DENIED,
                authorization_reason_code=f"{permission.value}_caller_not_allowed",
                document_id=document_id,
            )
        )
        raise AuthorizationFailedError(f"{permission.value}_caller_not_allowed")

    def _allowed_callers_for(self, permission: ArchivePermission) -> frozenset[str]:
        if permission is ArchivePermission.CREATE_DOCUMENT:
            return self.create_callers
        if permission in {ArchivePermission.READ_METADATA, ArchivePermission.DOWNLOAD_BINARY}:
            return self.read_callers
        if permission is ArchivePermission.READ_RETENTION:
            return self.retention_callers
        if permission in {ArchivePermission.EVALUATE_PURGE, ArchivePermission.EXECUTE_PURGE}:
            return self.purge_callers
        if permission is ArchivePermission.MANAGE_LEGAL_HOLD:
            return self.legal_hold_callers
        if permission is ArchivePermission.MANAGE_LIFECYCLE:
            return self.lifecycle_callers
        if permission is ArchivePermission.READ_IDEA_LIFECYCLE_DECISION:
            return self.idea_lifecycle_decision_callers
        if permission is ArchivePermission.READ_BATCH_ACCESS_PREFLIGHT:
            return self.batch_access_preflight_callers
        return self.audit_callers

    def document_scope_decision(
        self,
        *,
        metadata: ArchiveDocumentMetadata,
        caller_context: CallerContext,
    ) -> ArchiveAccessDecision:
        if not caller_context.tenant_id or not caller_context.region:
            return ArchiveAccessDecision(
                state=ArchiveAccessState.DENIED,
                reason_code=ArchiveAccessReasonCode.CALLER_SCOPE_MISMATCH,
            )
        if not metadata.tenant_id or not metadata.region:
            return ArchiveAccessDecision(
                state=ArchiveAccessState.UNAVAILABLE,
                reason_code=ArchiveAccessReasonCode.DOCUMENT_SCOPE_UNAVAILABLE,
            )
        if (
            metadata.tenant_id != caller_context.tenant_id
            or metadata.region.casefold() != caller_context.region.casefold()
        ):
            return ArchiveAccessDecision(
                state=ArchiveAccessState.DENIED,
                reason_code=ArchiveAccessReasonCode.CALLER_SCOPE_MISMATCH,
            )
        if metadata.purge_status is PurgeStatus.PURGED:
            return ArchiveAccessDecision(
                state=ArchiveAccessState.UNAVAILABLE,
                reason_code=ArchiveAccessReasonCode.DOCUMENT_PURGED,
            )
        return ArchiveAccessDecision(
            state=ArchiveAccessState.ALLOWED,
            reason_code=ArchiveAccessReasonCode.ACCESS_ALLOWED,
        )

    def authorize_document_scope(
        self,
        *,
        metadata: ArchiveDocumentMetadata,
        caller_context: CallerContext,
        audit_repository: AccessAuditRepository,
        trace_id: str,
    ) -> None:
        require_caller_scope(caller_context)
        decision = self.document_scope_decision(
            metadata=metadata,
            caller_context=caller_context,
        )
        if decision.state is ArchiveAccessState.ALLOWED:
            return
        audit_repository.record(
            access_audit_event(
                event_type=AccessEventType.AUTHORIZATION_DENIED,
                caller_context=caller_context,
                trace_id=trace_id,
                authorization_decision=AuthorizationDecision.DENIED,
                authorization_reason_code=decision.reason_code.value,
                document_id=metadata.document_id,
            )
        )
        raise AuthorizationFailedError(decision.reason_code.value)


def require_caller_scope(caller_context: CallerContext) -> None:
    missing = tuple(
        header
        for header, value in (
            ("x-tenant-id", caller_context.tenant_id),
            ("x-region", caller_context.region),
        )
        if not value
    )
    if missing:
        raise CallerScopeMissingError(missing)
