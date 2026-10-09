"""Exact Report monthly amendment custody; no source eligibility evaluation."""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.archive.composite_eligibility import (
    EligibilitySelection,
    EvaluatedEligibilityPin,
    PublishedEligibilityPin,
)
from app.archive.composite_identity import Digest, Identifier


class MonthlyReceiptPin(BaseModel):
    """Caller-pinned retained monthly receipt; no latest authority inference."""

    model_config = ConfigDict(extra="forbid")
    product_version: Literal["v1", "v2"]
    evaluation_revision: Identifier
    approval_content_hash: Digest
    receipt_content_hash: Digest
    receipt_response_digest: Digest


class AmendmentEvaluatedPin(EvaluatedEligibilityPin):
    lineage_receipts: list[MonthlyReceiptPin] = Field(min_length=1, max_length=31)


class AmendmentPublishedPin(PublishedEligibilityPin):
    lineage_receipts: list[MonthlyReceiptPin] = Field(min_length=1, max_length=31)
    parent_publication_response_digest: Digest


class AmendmentEligibilitySelection(BaseModel):
    """Explicit source-v2 ordinary-month selection; independent definition version."""

    model_config = ConfigDict(extra="forbid")
    selection_version: Literal["v2"]
    tenant_id: Identifier
    composite_id: Identifier
    definition_version: Identifier
    reporting_currency: str = Field(pattern=r"^[A-Z]{3}$")
    period_start: date
    period_end: date
    months: list[
        Annotated[
            AmendmentPublishedPin | AmendmentEvaluatedPin, Field(discriminator="evidence_kind")
        ]
    ] = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def require_ordered_months(self) -> Self:
        plain = self.model_dump(mode="json", exclude={"selection_version"})
        for month in plain["months"]:
            month.pop("lineage_receipts")
            month.pop("parent_publication_response_digest", None)
        EligibilitySelection.model_validate(plain)
        return self


class CompositeReportIdentityV6(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["composite_review.v6"]
    qualification: Literal["CONTROLLED_MONTHLY_SOURCE_AMENDMENT_REPLAY"]
    publication_state: Literal["NOT_ATTESTED"]
    selection: AmendmentEligibilitySelection
    series_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_revision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    factual_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
