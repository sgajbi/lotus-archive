"""Lifecycle transition preconditions, validated where the write happens.

Extracted from `ArchiveDocumentService` so the SAME decision can run at two
levels of authority: once in the service against unlocked reads, for a fast
refusal with a precise error, and once inside each repository's transaction
against the rows it has just locked, where the answer cannot go stale before
the write. The service copy alone was the C6-ARC-01B defect (issue #166): a
validation taken from a snapshot authorizes nothing about the row that is
actually written, and the whole-snapshot write that followed it could revert a
purge or hold another writer had committed in between.
"""

from __future__ import annotations

from app.archive.exceptions import (
    SupersessionConflictError,
    UnsupportedLifecycleTransitionError,
)
from app.archive.models import (
    LIFECYCLE_TARGET_ORIGIN_FIELD,
    ArchiveDocumentMetadata,
    LifecycleTransitionType,
    PurgeStatus,
)


def validate_lifecycle_preconditions(
    *,
    source: ArchiveDocumentMetadata,
    target: ArchiveDocumentMetadata,
    transition_type: LifecycleTransitionType,
) -> None:
    """Refuse every state a transition must not overwrite. Raises, never repairs."""
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


def transition_pointers_agree(
    *,
    source: ArchiveDocumentMetadata,
    target: ArchiveDocumentMetadata,
    transition_type: LifecycleTransitionType,
) -> bool:
    """True when both documents already record exactly this transition.

    Recognises an idempotent replay: the source points at this target and the
    target's origin field for this transition type points back. Anything less
    is a genuine conflict for the validation above to refuse.
    """
    origin_field = LIFECYCLE_TARGET_ORIGIN_FIELD.get(transition_type)
    if origin_field is None:
        return False
    if source.superseded_by_document_id != target.document_id:
        return False
    return getattr(target, origin_field) == source.document_id
