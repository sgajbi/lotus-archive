from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.archive.audit import AccessAuditEvent
from app.archive.models import (
    ArchiveDocumentInput,
    ArchiveDocumentMetadata,
    DocumentClassification,
    LegalHoldStatus,
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
    report_type: str = Field(description="Generated report type.")
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
