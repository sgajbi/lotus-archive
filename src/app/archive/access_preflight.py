from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from app.archive.authorization import ArchiveAuthorizationPolicy
    from app.security.caller_context import CallerContext
    from app.archive.models import ArchiveDocumentMetadata

# One bound, enforced at both the API model and the service, so a non-HTTP caller or a moved
# validation layer cannot silently widen the batch (issue #88).
MAX_PREFLIGHT_DOCUMENT_IDS = 100


class ArchiveAccessState(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    UNAVAILABLE = "unavailable"


class ArchiveAccessReasonCode(StrEnum):
    ACCESS_ALLOWED = "access_allowed"
    CALLER_SCOPE_MISMATCH = "caller_scope_mismatch"
    DOCUMENT_NOT_FOUND = "document_not_found"
    DOCUMENT_PURGED = "document_purged"
    DOCUMENT_SCOPE_UNAVAILABLE = "document_scope_unavailable"
    LOOKUP_UNAVAILABLE = "lookup_unavailable"
    NOT_ACCESSIBLE = "not_accessible"


# Reason codes that reveal whether a document exists outside the caller's scope. They are audit
# truth, never response truth: the caller-facing item for any of them is DENIED/not_accessible,
# so a batch of ids cannot be used to partition another tenant's archive into
# "exists" and "does not exist" (issue #88).
EXISTENCE_REVEALING_REASON_CODES = frozenset(
    {
        ArchiveAccessReasonCode.DOCUMENT_NOT_FOUND,
        ArchiveAccessReasonCode.CALLER_SCOPE_MISMATCH,
        ArchiveAccessReasonCode.DOCUMENT_SCOPE_UNAVAILABLE,
    }
)

# The only reason codes a preflight RESPONSE may carry. Everything else is audit vocabulary.
# The API response model validates against this subset, so a future change that leaks a granular
# reason into the response fails contract validation instead of shipping.
RESPONSE_REASON_CODES = frozenset(
    {
        ArchiveAccessReasonCode.ACCESS_ALLOWED,
        ArchiveAccessReasonCode.NOT_ACCESSIBLE,
        ArchiveAccessReasonCode.LOOKUP_UNAVAILABLE,
        ArchiveAccessReasonCode.DOCUMENT_PURGED,
    }
)


class ArchiveAccessResultState(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ArchiveAccessDecision:
    state: ArchiveAccessState
    reason_code: ArchiveAccessReasonCode


@dataclass(frozen=True)
class ArchiveAccessPreflightItem:
    document_id: str
    state: ArchiveAccessState
    reason_code: ArchiveAccessReasonCode


@dataclass(frozen=True)
class ArchiveAccessPreflightResult:
    items: tuple[ArchiveAccessPreflightItem, ...]
    result_state: ArchiveAccessResultState


def result_state_for_items(
    items: tuple[ArchiveAccessPreflightItem, ...],
) -> ArchiveAccessResultState:
    unavailable_count = sum(item.state is ArchiveAccessState.UNAVAILABLE for item in items)
    if unavailable_count == len(items):
        return ArchiveAccessResultState.UNAVAILABLE
    if unavailable_count:
        return ArchiveAccessResultState.PARTIAL
    return ArchiveAccessResultState.COMPLETE


def preflight_item(
    *,
    document_id: str,
    metadata: "ArchiveDocumentMetadata | None",
    unavailable: bool,
    caller_context: "CallerContext",
    authorization_policy: "ArchiveAuthorizationPolicy",
) -> tuple[ArchiveAccessPreflightItem, ArchiveAccessReasonCode]:
    """Return the caller-facing item plus the granular reason for the audit record.

    The two deliberately diverge for existence-revealing outcomes: a missing id, a
    cross-tenant id, and a scope-less record all present as DENIED/not_accessible, so the
    response cannot be used as an existence oracle. The audit keeps the real reason.

    Lives here rather than on the service because it is a decision about preflight
    state, not an orchestration step: it reads a policy and a record and returns a
    result, with nothing to persist and nothing to sequence.
    """
    if unavailable:
        item = ArchiveAccessPreflightItem(
            document_id=document_id,
            state=ArchiveAccessState.UNAVAILABLE,
            reason_code=ArchiveAccessReasonCode.LOOKUP_UNAVAILABLE,
        )
        return item, ArchiveAccessReasonCode.LOOKUP_UNAVAILABLE
    if metadata is None:
        granular = ArchiveAccessReasonCode.DOCUMENT_NOT_FOUND
    else:
        decision = authorization_policy.document_scope_decision(
            metadata=metadata,
            caller_context=caller_context,
        )
        granular = decision.reason_code
    if granular in EXISTENCE_REVEALING_REASON_CODES:
        item = ArchiveAccessPreflightItem(
            document_id=document_id,
            state=ArchiveAccessState.DENIED,
            reason_code=ArchiveAccessReasonCode.NOT_ACCESSIBLE,
        )
        return item, granular
    item = ArchiveAccessPreflightItem(
        document_id=document_id,
        state=decision.state,
        reason_code=decision.reason_code,
    )
    return item, granular
