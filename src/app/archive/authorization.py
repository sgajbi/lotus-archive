from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.archive.audit import (
    AccessAuditRepository,
    AccessEventType,
    AuthorizationDecision,
    access_audit_event,
)
from app.security.caller_context import CallerContext


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


class AuthorizationFailedError(PermissionError):
    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


@dataclass(frozen=True)
class ArchiveAuthorizationPolicy:
    create_callers: frozenset[str] = frozenset({"lotus-report"})
    read_callers: frozenset[str] = frozenset({"lotus-report", "lotus-gateway"})
    audit_callers: frozenset[str] = frozenset({"lotus-report"})
    retention_callers: frozenset[str] = frozenset({"lotus-report"})
    purge_callers: frozenset[str] = frozenset({"lotus-report"})
    legal_hold_callers: frozenset[str] = frozenset({"lotus-report"})
    lifecycle_callers: frozenset[str] = frozenset({"lotus-report"})

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
        return self.audit_callers
