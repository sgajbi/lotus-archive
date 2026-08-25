from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ArchiveAccessState(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    MISSING = "missing"
    UNAVAILABLE = "unavailable"


class ArchiveAccessReasonCode(StrEnum):
    ACCESS_ALLOWED = "access_allowed"
    CALLER_SCOPE_MISMATCH = "caller_scope_mismatch"
    DOCUMENT_NOT_FOUND = "document_not_found"
    DOCUMENT_PURGED = "document_purged"
    DOCUMENT_SCOPE_UNAVAILABLE = "document_scope_unavailable"
    LOOKUP_UNAVAILABLE = "lookup_unavailable"


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
