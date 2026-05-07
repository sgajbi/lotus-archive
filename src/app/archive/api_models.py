from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.archive.audit import AccessAuditEvent
from app.archive.models import (
    ArchiveDocumentInput,
    ArchiveDocumentMetadata,
    DocumentClassification,
    GeneratedReportType,
    LegalHoldStatus,
    LegalHoldRecord,
    LifecycleRelationshipRecord,
    LifecycleTransitionType,
    PurgeStatus,
)


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
        description="Business reason for the lifecycle transition.",
    )


class LifecycleRelationshipResponse(BaseModel):
    lifecycle_relationship_id: str = Field(description="Stable lifecycle relationship identifier.")
    source_document_id: str = Field(description="Historical archived document identifier.")
    target_document_id: str = Field(description="Current archived document identifier.")
    transition_type: LifecycleTransitionType = Field(description="Lifecycle transition type.")
    transition_reason: str = Field(description="Business reason for the lifecycle transition.")
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
