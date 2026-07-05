from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.archive.audit import AccessAuditEvent
from app.archive.models import (
    ArchiveDocumentInput,
    ArchiveDocumentMetadata,
    AdvisorProposalMemoArchiveSummary,
    DocumentClassification,
    GeneratedReportType,
    LegalHoldStatus,
    LegalHoldRecord,
    LifecycleRelationshipRecord,
    LifecycleTransitionType,
    PurgeStatus,
    ReviewedAdvisoryNarrativeArchiveSummary,
)
from app.archive.source_events import SOURCE_EVENT_FAMILY


class ArchiveDocumentCreateRequest(BaseModel):
    metadata: ArchiveDocumentInput = Field(
        description="Source-backed metadata for the generated document being archived."
    )
    content_base64: str = Field(
        min_length=1,
        description="Base64-encoded generated document binary.",
        examples=["JVBERi0xLjQKJcTl8uXr"],
    )


class ArchiveDocumentResponse(BaseModel):
    document_id: str = Field(description="Stable archive document identifier.")
    archive_request_id: str = Field(description="Idempotency key supplied by the archive caller.")
    report_job_id: str = Field(description="Source report job identifier.")
    report_request_id: str = Field(description="Source report request identifier.")
    snapshot_id: str = Field(description="Report data snapshot identifier.")
    render_job_id: str = Field(description="Render job identifier.")
    render_attempt_id: str = Field(description="Render attempt identifier.")
    report_type: GeneratedReportType = Field(description="Generated report type.")
    portfolio_scope: str = Field(description="Portfolio scope represented by the document.")
    portfolio_id: str = Field(description="Portfolio identifier represented by the document.")
    client_reference: str | None = Field(
        default=None,
        description="Support-safe client reference when provided by the reporting source.",
    )
    as_of_date: date = Field(description="Report as-of date.")
    reporting_period_start: date = Field(description="Reporting period start date.")
    reporting_period_end: date = Field(description="Reporting period end date.")
    frequency: str = Field(description="Report frequency.")
    template_id: str = Field(description="Template identifier used for rendering.")
    template_version: str = Field(description="Template version used for rendering.")
    render_service_version: str = Field(description="Render service version.")
    report_data_contract_version: str = Field(description="Report data contract version.")
    checksum_algorithm: str = Field(description="Checksum algorithm used for integrity checks.")
    checksum: str = Field(description="Checksum of the archived binary.")
    size_bytes: int = Field(description="Archived binary size in bytes.")
    mime_type: str = Field(description="Archived binary media type.")
    output_format: str = Field(description="Archived output format.")
    classification: DocumentClassification = Field(description="Document classification.")
    region: str = Field(description="Region scope for the archive record.")
    tenant_id: str | None = Field(default=None, description="Tenant scope when available.")
    retention_policy_id: str | None = Field(
        default=None,
        description="Retention policy assigned to the document.",
    )
    retention_start_date: date | None = Field(
        default=None,
        description="Date retention starts for the document.",
    )
    retain_until_date: date | None = Field(
        default=None,
        description="Date until which the document must be retained.",
    )
    reviewed_advisory_narrative: ReviewedAdvisoryNarrativeArchiveSummary | None = Field(
        default=None,
        description=(
            "Support-safe reviewed advisory narrative archive summary when the portfolio-review "
            "document includes the RFC-0023 advisor-use narrative page. This does not expose raw "
            "narrative sections and does not promote client-ready status."
        ),
    )
    advisor_proposal_memo: AdvisorProposalMemoArchiveSummary | None = Field(
        default=None,
        description=(
            "Support-safe advisor proposal memo archive summary when the portfolio-review "
            "document includes an RFC-0024 advisor-use memo package. Client-ready memo document "
            "publication remains blocked."
        ),
    )
    purge_status: PurgeStatus = Field(description="Current purge eligibility status.")
    legal_hold_status: LegalHoldStatus = Field(description="Current legal-hold status.")
    legal_hold_count: int = Field(description="Number of active legal holds.")
    supersedes_document_id: str | None = Field(
        default=None,
        description="Document superseded by this document, when applicable.",
    )
    superseded_by_document_id: str | None = Field(
        default=None,
        description="Document that supersedes this document, when applicable.",
    )
    correction_of_document_id: str | None = Field(
        default=None,
        description="Document corrected by this document, when applicable.",
    )
    reissue_of_document_id: str | None = Field(
        default=None,
        description="Document reissued by this document, when applicable.",
    )
    created_by_service: str = Field(description="Service that created the archive record.")
    created_by_actor: str = Field(description="Actor that created the archive record.")
    created_at: datetime = Field(description="UTC timestamp when the archive record was created.")
    updated_at: datetime = Field(description="UTC timestamp when the archive record was updated.")

    @classmethod
    def from_metadata(cls, metadata: ArchiveDocumentMetadata) -> ArchiveDocumentResponse:
        return cls.model_validate(
            metadata.model_dump(
                exclude={
                    "storage_provider",
                    "storage_namespace",
                    "storage_key",
                    "purge_eligible_at",
                    "purged_at",
                }
            )
        )


class AccessEventListResponse(BaseModel):
    document_id: str = Field(description="Archived document identifier.")
    returned_count: int = Field(description="Number of access events returned in this page.")
    total_count: int = Field(description="Total available access events before pagination.")
    limit: int = Field(description="Requested page limit after server-side validation.")
    offset: int = Field(description="Zero-based event offset for this page.")
    next_offset: int | None = Field(
        default=None,
        description="Next offset when more access events are available.",
    )
    events: list[AccessAuditEvent] = Field(description="Access-audit events for this document.")


class RetentionResponse(BaseModel):
    document_id: str = Field(description="Archived document identifier.")
    retention_policy_id: str | None = Field(
        default=None,
        description="Retention policy assigned to the document.",
    )
    retention_start_date: date | None = Field(
        default=None,
        description="Date retention starts for the document.",
    )
    retain_until_date: date | None = Field(
        default=None,
        description="Date until which the document must be retained.",
    )
    purge_eligible_at: datetime | None = Field(
        default=None,
        description="Timestamp when the document became purge-eligible.",
    )
    purged_at: datetime | None = Field(
        default=None,
        description="Timestamp when purge execution completed.",
    )
    purge_status: PurgeStatus = Field(description="Current purge status.")
    legal_hold_status: LegalHoldStatus = Field(description="Current legal-hold status.")
    legal_hold_count: int = Field(description="Number of active legal holds.")

    @classmethod
    def from_metadata(cls, metadata: ArchiveDocumentMetadata) -> RetentionResponse:
        return cls(
            document_id=metadata.document_id,
            retention_policy_id=metadata.retention_policy_id,
            retention_start_date=metadata.retention_start_date,
            retain_until_date=metadata.retain_until_date,
            purge_eligible_at=metadata.purge_eligible_at,
            purged_at=metadata.purged_at,
            purge_status=metadata.purge_status,
            legal_hold_status=metadata.legal_hold_status,
            legal_hold_count=metadata.legal_hold_count,
        )


class PurgeEvaluationResponse(RetentionResponse):
    purge_eligible: bool = Field(description="Whether purge execution is currently allowed.")
    reason_code: str = Field(description="Stable support-safe purge eligibility reason code.")


class PurgeExecutionResponse(RetentionResponse):
    purged: bool = Field(description="Whether this request completed or confirmed purge execution.")
    reason_code: str = Field(description="Stable support-safe purge execution reason code.")


class LegalHoldCreateRequest(BaseModel):
    hold_reason: str = Field(min_length=1, description="Reason the legal hold is required.")
    authority_reference: str = Field(
        min_length=1,
        description="Legal, compliance, or operational authority reference for the hold.",
    )


class LegalHoldReleaseRequest(BaseModel):
    release_reason: str = Field(
        min_length=1, description="Reason the legal hold is being released."
    )


class LegalHoldResponse(BaseModel):
    legal_hold_id: str = Field(description="Stable legal-hold identifier.")
    document_id: str = Field(description="Archived document identifier.")
    hold_status: LegalHoldStatus = Field(description="Current legal-hold status.")
    hold_reason: str = Field(description="Reason the legal hold was set.")
    authority_reference: str = Field(description="Authority reference for the legal hold.")
    requested_by: str = Field(description="Actor that requested the legal hold.")
    requested_at: datetime = Field(description="UTC timestamp when the legal hold was requested.")
    released_by: str | None = Field(default=None, description="Actor that released the legal hold.")
    released_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when the legal hold was released.",
    )
    release_reason: str | None = Field(
        default=None,
        description="Reason the legal hold was released.",
    )

    @classmethod
    def from_record(cls, record: LegalHoldRecord) -> LegalHoldResponse:
        return cls.model_validate(record.model_dump())


class LifecycleTransitionRequest(BaseModel):
    target_document_id: str = Field(
        min_length=1,
        description="Archived document that becomes the current document for this transition.",
    )
    transition_reason: str = Field(
        min_length=1,
        max_length=200,
        description="Business reason for the lifecycle transition.",
    )

    @field_validator("transition_reason")
    @classmethod
    def _transition_reason_must_be_support_safe(cls, value: str) -> str:
        lowered = value.lower()
        blocked_tokens = (
            "client-ref",
            "client_reference",
            "storage_key",
            "s3://",
            "raw_payload",
            "trace_id",
            "correlation_id",
        )
        if any(token in lowered for token in blocked_tokens):
            raise ValueError("transition_reason must not contain sensitive support identifiers")
        return value


class LifecycleRelationshipResponse(BaseModel):
    lifecycle_relationship_id: str = Field(description="Stable lifecycle relationship identifier.")
    source_document_id: str = Field(description="Historical archived document identifier.")
    target_document_id: str = Field(description="Current archived document identifier.")
    transition_type: LifecycleTransitionType = Field(description="Lifecycle transition type.")
    transition_reason: str = Field(description="Business reason for the lifecycle transition.")
    transition_reason_code: str = Field(
        description="Stable support-safe lifecycle reason code for downstream consumers."
    )
    requested_by: str = Field(description="Actor that requested the lifecycle transition.")
    requested_at: datetime = Field(
        description="UTC timestamp when the lifecycle transition was requested."
    )
    current_document_id: str = Field(
        description="Current archived document identifier after resolving lifecycle history."
    )

    @classmethod
    def from_record(
        cls,
        record: LifecycleRelationshipRecord,
        *,
        current_document_id: str,
    ) -> LifecycleRelationshipResponse:
        return cls(
            **record.model_dump(),
            current_document_id=current_document_id,
        )


class ArchiveArtifactRef(BaseModel):
    artifact_type: str = Field(description="Support-safe artifact reference type.")
    artifact_id: str = Field(description="Stable artifact identifier.")
    content_hash: str | None = Field(
        default=None,
        description="Artifact content hash when available without exposing raw payloads.",
    )


class ArchiveDocumentSourceEvent(BaseModel):
    event_id: str = Field(description="Stable archive-owned source-event identifier.")
    event_type: str = Field(
        description=(
            "Archive-owned source-event type for generated-document lifecycle or client-delivery "
            "lineage."
        )
    )
    occurred_at: datetime = Field(description="UTC timestamp for the source event.")
    source_system: str = Field(description="Source system emitting the event.")
    source_event_family: str = Field(description="Governed source-event family identifier.")
    source_type: str = Field(description="Archive source record type behind this event.")
    source_id: str = Field(description="Archive source record identifier behind this event.")
    portfolio_id: str = Field(description="Portfolio represented by the archived document.")
    report_type: GeneratedReportType = Field(description="Generated report type.")
    report_job_id: str = Field(description="Source report job identifier.")
    snapshot_id: str = Field(description="Source report snapshot identifier.")
    render_job_id: str = Field(description="Source render job identifier.")
    render_attempt_id: str = Field(description="Source render attempt identifier.")
    document_id: str = Field(description="Archived document represented by this source event.")
    current_document_id: str = Field(
        description="Current archived document in the lifecycle chain."
    )
    related_document_id: str | None = Field(
        default=None,
        description="Related historical or current document for lifecycle events.",
    )
    transition_reason_code: str | None = Field(
        default=None,
        description="Stable support-safe lifecycle transition reason code for source events.",
    )
    delivery_mode: str = Field(description="Source-event publication mode.")
    replay_contract: str = Field(description="Source-event replay and idempotency contract.")
    source_owner: str = Field(description="Source owner for generated document facts.")
    document_evidence_authority: str = Field(
        description="Archive authority boundary for this source event."
    )
    report_data_contract_version: str = Field(
        description="Report input contract version supplied by lotus-report."
    )
    template_id: str = Field(description="Render template identifier supplied by lotus-report.")
    template_version: str = Field(description="Render template version supplied by lotus-report.")
    content_hash: str = Field(description="Checksum-backed content hash for the archived artifact.")
    supportability_state: str = Field(description="Source-event supportability state.")
    reason_codes: list[str] = Field(description="Stable reason codes for downstream consumers.")
    retention_policy: str = Field(description="Retention policy for the source event projection.")
    redaction_policy: str = Field(description="Redaction policy for the source event projection.")
    audit_policy: str = Field(description="Audit policy covering the source event projection.")
    access_classification: str = Field(
        description="Access classification for downstream source-event consumers."
    )
    artifact_refs: list[ArchiveArtifactRef] = Field(
        description="Bounded artifact references without raw document bytes or storage keys."
    )


class ArchiveDocumentSourceEventsResponse(BaseModel):
    service: str = Field(description="Service emitting archive source events.")
    source_event_family: str = Field(
        default=SOURCE_EVENT_FAMILY,
        description="Governed archive source-event family identifier.",
    )
    document_id: str = Field(description="Archived document used as the source-event anchor.")
    current_document_id: str = Field(
        description="Current archived document in the lifecycle chain."
    )
    portfolio_id: str = Field(description="Portfolio represented by the archived document.")
    report_type: GeneratedReportType = Field(description="Generated report type.")
    event_count: int = Field(description="Number of returned source events.")
    returned_count: int = Field(description="Number of events returned in this page.")
    total_count: int = Field(description="Total available source events before pagination.")
    limit: int = Field(description="Requested page limit after server-side validation.")
    offset: int = Field(description="Zero-based event offset for this page.")
    next_offset: int | None = Field(
        default=None,
        description="Next offset when more source events are available.",
    )
    delivery_mode: str = Field(description="Pull-only source-event delivery mode.")
    replay_contract: str = Field(description="Deterministic replay and idempotency contract.")
    no_raw_payloads: bool = Field(
        description="Whether raw document bytes, storage keys, and client references are omitted."
    )
    latest_event_at: datetime | None = Field(
        default=None,
        description="UTC timestamp for the latest returned source event.",
    )
    events: list[ArchiveDocumentSourceEvent] = Field(
        description="Archive-owned generated-document source events ordered by event time."
    )
