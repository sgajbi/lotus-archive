from __future__ import annotations

from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.archive.checksum import SUPPORTED_CHECKSUM_ALGORITHM


class PurgeStatus(StrEnum):
    NOT_ELIGIBLE = "not_eligible"
    ELIGIBLE = "eligible"
    PURGED = "purged"


class LegalHoldStatus(StrEnum):
    CLEAR = "clear"
    ACTIVE = "active"


class LifecycleTransitionType(StrEnum):
    SUPERSEDE = "supersede"
    CORRECT = "correct"
    REISSUE = "reissue"


class DocumentClassification(StrEnum):
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class ArchiveDocumentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    archive_request_id: str = Field(min_length=1)
    report_job_id: str = Field(min_length=1)
    report_request_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    render_job_id: str = Field(min_length=1)
    render_attempt_id: str = Field(min_length=1)
    report_type: str = Field(min_length=1)
    portfolio_scope: str = Field(min_length=1)
    portfolio_id: str = Field(min_length=1)
    client_reference: str | None = Field(default=None, min_length=1)
    as_of_date: date
    reporting_period_start: date
    reporting_period_end: date
    frequency: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    template_version: str = Field(min_length=1)
    render_service_version: str = Field(min_length=1)
    report_data_contract_version: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    output_format: str = Field(min_length=1)
    classification: DocumentClassification
    region: str = Field(min_length=1)
    tenant_id: str | None = Field(default=None, min_length=1)
    retention_policy_id: str | None = Field(default=None, min_length=1)
    retention_start_date: date | None = None
    retain_until_date: date | None = None
    created_by_service: str = Field(min_length=1)
    created_by_actor: str = Field(min_length=1)

    @field_validator("mime_type")
    @classmethod
    def _mime_type_must_be_specific(cls, value: str) -> str:
        if "/" not in value:
            raise ValueError("mime_type must use a concrete media type")
        return value

    @model_validator(mode="after")
    def _dates_must_be_ordered(self) -> Self:
        if self.reporting_period_start > self.reporting_period_end:
            raise ValueError("reporting_period_start must be on or before reporting_period_end")
        if self.retain_until_date and self.retention_start_date:
            if self.retention_start_date > self.retain_until_date:
                raise ValueError("retention_start_date must be on or before retain_until_date")
        return self


class ArchiveDocumentMetadata(ArchiveDocumentInput):
    document_id: str = Field(min_length=1)
    storage_provider: str = Field(min_length=1)
    storage_namespace: str = Field(min_length=1)
    storage_key: str = Field(min_length=1)
    checksum_algorithm: str = Field(default=SUPPORTED_CHECKSUM_ALGORITHM)
    checksum: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=0)
    purge_eligible_at: datetime | None = None
    purged_at: datetime | None = None
    purge_status: PurgeStatus = PurgeStatus.NOT_ELIGIBLE
    legal_hold_status: LegalHoldStatus = LegalHoldStatus.CLEAR
    legal_hold_count: int = Field(default=0, ge=0)
    supersedes_document_id: str | None = None
    superseded_by_document_id: str | None = None
    correction_of_document_id: str | None = None
    reissue_of_document_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("checksum_algorithm")
    @classmethod
    def _checksum_algorithm_must_be_supported(cls, value: str) -> str:
        normalized = value.lower()
        if normalized != SUPPORTED_CHECKSUM_ALGORITHM:
            raise ValueError("checksum_algorithm must be sha256")
        return normalized


class LegalHoldRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    legal_hold_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    hold_status: LegalHoldStatus = LegalHoldStatus.ACTIVE
    hold_reason: str = Field(min_length=1)
    authority_reference: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    released_by: str | None = Field(default=None, min_length=1)
    released_at: datetime | None = None
    release_reason: str | None = Field(default=None, min_length=1)


class LifecycleRelationshipRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    lifecycle_relationship_id: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    target_document_id: str = Field(min_length=1)
    transition_type: LifecycleTransitionType
    transition_reason: str = Field(min_length=1)
    requested_by: str = Field(min_length=1)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
