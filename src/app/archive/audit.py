from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from app.security.caller_context import CallerContext


class AccessEventType(StrEnum):
    ARCHIVE_CREATE = "archive_create"
    METADATA_READ = "metadata_read"
    BINARY_DOWNLOAD = "binary_download"
    ACCESS_EVENTS_READ = "access_events_read"
    RETENTION_READ = "retention_read"
    PURGE_EVALUATION = "purge_evaluation"
    PURGE_EXECUTION = "purge_execution"
    LEGAL_HOLD_SET = "legal_hold_set"
    LEGAL_HOLD_RELEASE = "legal_hold_release"
    LIFECYCLE_SUPERSEDE = "lifecycle_supersede"
    LIFECYCLE_CORRECT = "lifecycle_correct"
    LIFECYCLE_REISSUE = "lifecycle_reissue"
    CURRENT_DOCUMENT_READ = "current_document_read"
    AUTHORIZATION_DENIED = "authorization_denied"


class AuthorizationDecision(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"


class AccessAuditEvent(BaseModel):
    audit_event_id: str = Field(description="Stable archive access-audit event identifier.")
    document_id: str | None = Field(
        default=None,
        description="Archived document identifier when the event is tied to one document.",
    )
    event_type: AccessEventType = Field(description="Archive access or mutation event type.")
    actor_type: str = Field(description="Caller actor type supplied by caller context.")
    actor_id: str = Field(description="Caller actor identifier supplied by caller context.")
    caller_service: str = Field(description="Calling Lotus service.")
    authorization_decision: AuthorizationDecision = Field(
        description="Authorization decision applied by lotus-archive."
    )
    authorization_reason_code: str = Field(
        description="Stable support-safe reason code for the authorization decision."
    )
    correlation_id: str = Field(description="Correlation identifier for support tracing.")
    trace_id: str = Field(description="Trace identifier for cross-service tracing.")
    created_at: datetime = Field(description="UTC timestamp when the audit event was recorded.")


class AccessAuditRepository(Protocol):
    def record(self, event: AccessAuditEvent) -> AccessAuditEvent: ...

    def list_by_document_id(self, document_id: str | None) -> list[AccessAuditEvent]: ...


class InMemoryAccessAuditRepository:
    def __init__(self) -> None:
        self._events: list[AccessAuditEvent] = []

    def record(self, event: AccessAuditEvent) -> AccessAuditEvent:
        self._events.append(event)
        return event

    def list_by_document_id(self, document_id: str | None) -> list[AccessAuditEvent]:
        return [event for event in self._events if event.document_id == document_id]


def access_audit_event(
    *,
    event_type: AccessEventType,
    caller_context: CallerContext,
    trace_id: str,
    authorization_decision: AuthorizationDecision,
    authorization_reason_code: str,
    document_id: str | None = None,
) -> AccessAuditEvent:
    return AccessAuditEvent(
        audit_event_id=f"audit_{uuid4().hex}",
        document_id=document_id,
        event_type=event_type,
        actor_type=caller_context.actor_type,
        actor_id=caller_context.actor_id,
        caller_service=caller_context.caller_service,
        authorization_decision=authorization_decision,
        authorization_reason_code=authorization_reason_code,
        correlation_id=caller_context.correlation_id,
        trace_id=trace_id,
        created_at=datetime.now(timezone.utc),
    )
