from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

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
