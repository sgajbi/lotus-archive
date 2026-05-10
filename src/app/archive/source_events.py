from __future__ import annotations

from datetime import datetime

from app.archive.models import (
    ArchiveDocumentMetadata,
    LifecycleRelationshipRecord,
    LifecycleTransitionType,
)

SOURCE_EVENT_FAMILY = "lotus-archive.generated_document_client_communication.v1"
SOURCE_SYSTEM = "lotus-archive"
RETENTION_POLICY = "archive_document_retention_policy"
REDACTION_POLICY = "NO_RAW_DOCUMENT_BYTES_NO_STORAGE_KEYS_NO_CLIENT_REFERENCE"
AUDIT_POLICY = "archive_access_and_lifecycle_audit"
ACCESS_CLASSIFICATION = "restricted"


def build_archive_document_source_events(
    *,
    metadata: ArchiveDocumentMetadata,
    current_document_id: str,
    lifecycle_relationships: list[LifecycleRelationshipRecord],
) -> list[dict[str, object]]:
    events = [_archive_created_event(metadata=metadata, current_document_id=current_document_id)]
    events.extend(
        _lifecycle_event(
            metadata=metadata,
            current_document_id=current_document_id,
            relationship=relationship,
        )
        for relationship in sorted(
            lifecycle_relationships,
            key=lambda item: (item.requested_at, item.lifecycle_relationship_id),
        )
    )
    return events


def _archive_created_event(
    *,
    metadata: ArchiveDocumentMetadata,
    current_document_id: str,
) -> dict[str, object]:
    return {
        **_base_event(metadata=metadata, current_document_id=current_document_id),
        "event_id": f"archive:{metadata.document_id}:created",
        "event_type": "generated_document_archived",
        "occurred_at": metadata.created_at,
        "source_type": "archive_document",
        "source_id": metadata.document_id,
        "related_document_id": None,
        "reason_codes": ["archive_metadata_persisted", "generated_document_checksum_preserved"],
    }


def _lifecycle_event(
    *,
    metadata: ArchiveDocumentMetadata,
    current_document_id: str,
    relationship: LifecycleRelationshipRecord,
) -> dict[str, object]:
    event_type = _event_type_for_lifecycle(relationship.transition_type)
    return {
        **_base_event(metadata=metadata, current_document_id=current_document_id),
        "event_id": f"archive:{relationship.lifecycle_relationship_id}",
        "event_type": event_type,
        "occurred_at": relationship.requested_at,
        "source_type": "archive_lifecycle_relationship",
        "source_id": relationship.lifecycle_relationship_id,
        "related_document_id": (
            relationship.target_document_id
            if relationship.source_document_id == metadata.document_id
            else relationship.source_document_id
        ),
        "transition_reason": relationship.transition_reason,
        "reason_codes": [
            f"archive_lifecycle_{relationship.transition_type.value}",
            "client_delivery_reissue_evidence"
            if relationship.transition_type is LifecycleTransitionType.REISSUE
            else "archive_document_lifecycle_evidence",
        ],
    }


def _base_event(
    *,
    metadata: ArchiveDocumentMetadata,
    current_document_id: str,
) -> dict[str, object]:
    return {
        "source_system": SOURCE_SYSTEM,
        "source_event_family": SOURCE_EVENT_FAMILY,
        "portfolio_id": metadata.portfolio_id,
        "report_type": metadata.report_type.value,
        "report_job_id": metadata.report_job_id,
        "snapshot_id": metadata.snapshot_id,
        "render_job_id": metadata.render_job_id,
        "render_attempt_id": metadata.render_attempt_id,
        "document_id": metadata.document_id,
        "current_document_id": current_document_id,
        "content_hash": f"{metadata.checksum_algorithm}:{metadata.checksum}",
        "supportability_state": "READY",
        "retention_policy": metadata.retention_policy_id or RETENTION_POLICY,
        "redaction_policy": REDACTION_POLICY,
        "audit_policy": AUDIT_POLICY,
        "access_classification": ACCESS_CLASSIFICATION,
        "artifact_refs": [
            {
                "artifact_type": "archive_document_metadata",
                "artifact_id": metadata.document_id,
                "content_hash": f"{metadata.checksum_algorithm}:{metadata.checksum}",
            },
            {
                "artifact_type": "report_job",
                "artifact_id": metadata.report_job_id,
            },
            {
                "artifact_type": "render_attempt",
                "artifact_id": metadata.render_attempt_id,
            },
        ],
    }


def _event_type_for_lifecycle(transition_type: LifecycleTransitionType) -> str:
    if transition_type is LifecycleTransitionType.SUPERSEDE:
        return "generated_document_superseded"
    if transition_type is LifecycleTransitionType.CORRECT:
        return "generated_document_corrected"
    if transition_type is LifecycleTransitionType.REISSUE:
        return "client_delivery_document_reissued"
    return "generated_document_lifecycle_updated"


def latest_event_time(events: list[dict[str, object]]) -> datetime | None:
    if not events:
        return None
    return max(
        event["occurred_at"] for event in events if isinstance(event["occurred_at"], datetime)
    )
