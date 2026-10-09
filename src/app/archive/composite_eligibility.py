"""Strict Report-owned Manage eligibility pins, without source rule evaluation."""

from calendar import monthrange
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.archive.composite_identity import Digest, Identifier

Month = Annotated[str, Field(pattern=r"^[0-9]{4}-(?:0[1-9]|1[0-2])$")]


class EvaluatedEligibilityPin(BaseModel):
    """Exact retained proposal; never implies checker approval or publication."""

    model_config = ConfigDict(extra="forbid")

    evidence_kind: Literal["EVALUATED_ONLY"]
    month: Month
    evaluation_revision: Identifier
    proposal_content_hash: Digest
    proposal_response_digest: Digest
    parent_membership_revision: Identifier
    parent_membership_content_hash: Digest
    source_cut_id: Identifier


class PublishedEligibilityPin(BaseModel):
    """Whole publication custody plus independently pinned canonical products."""

    model_config = ConfigDict(extra="forbid")

    evidence_kind: Literal["PUBLISHED"]
    month: Month
    evaluation_revision: Identifier
    proposal_content_hash: Digest
    approval_content_hash: Digest
    receipt_content_hash: Digest
    receipt_response_digest: Digest
    membership_revision: Identifier
    membership_content_hash: Digest
    membership_response_digest: Digest
    attestation_version: Identifier
    universe_content_hash: Digest
    universe_response_digest: Digest
    parent_membership_revision: Identifier
    parent_membership_content_hash: Digest
    parent_response_digest: Digest
    publication_sequence: int = Field(gt=0, strict=True)
    publication_response_digest: Digest
    source_cut_id: Identifier


EligibilityMonthPin = Annotated[
    PublishedEligibilityPin | EvaluatedEligibilityPin, Field(discriminator="evidence_kind")
]


class EligibilitySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: Identifier
    composite_id: Identifier
    definition_version: Identifier
    reporting_currency: str = Field(pattern=r"^[A-Z]{3}$")
    period_start: date
    period_end: date
    months: list[EligibilityMonthPin] = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def ordered_selected_months(self) -> Self:
        months = [pin.month for pin in self.months]
        if months != sorted(set(months)) or self.period_end < self.period_start:
            raise ValueError("eligibility months must be unique and chronological")
        if (months[0], months[-1]) != (
            self.period_start.strftime("%Y-%m"),
            self.period_end.strftime("%Y-%m"),
        ):
            raise ValueError("eligibility pins must match the selected horizon")
        if (
            self.period_start.day != 1
            or self.period_end.day != monthrange(self.period_end.year, self.period_end.month)[1]
        ):
            raise ValueError("eligibility selection requires complete calendar months")
        # Report permits explicit gaps; Archive must not invent intervening evidence.
        return self


class CompositeReportIdentityV4(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["composite_review.v4"]
    qualification: Literal["CONTROLLED_ELIGIBILITY_SOURCE_REPLAY"]
    publication_state: Literal["NOT_ATTESTED"]
    selection: EligibilitySelection
    series_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_revision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    factual_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
