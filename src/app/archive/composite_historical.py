"""Report-owned historical policy custody; no policy or cryptographic authority."""

from datetime import date
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, model_validator

from app.archive.composite_eligibility import (
    EligibilitySelection,
    EvaluatedEligibilityPin,
    PublishedEligibilityPin,
)
from app.archive.composite_identity import Digest, Identifier

CALCULATION_BOUNDARY = (
    "Configured-identity controlled producer custody only; no cryptographic or bank "
    "provenance acceptance, TWR, MWR, dispersion, contribution or model-fee calculation. "
    "CONTROLLED / NOT_ATTESTED."
)


class HistoricalReceiptPin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_version: Literal["v3", "v4"]
    evaluation_revision: Identifier
    approval_content_hash: Digest
    receipt_content_hash: Digest
    receipt_response_digest: Digest


class HistoricalEvaluatedRootPin(EvaluatedEligibilityPin):
    product_version: Literal["v3"]


class HistoricalPublishedRootPin(PublishedEligibilityPin):
    product_version: Literal["v3"]


class HistoricalEvaluatedCorrectionPin(EvaluatedEligibilityPin):
    product_version: Literal["v4"]
    lineage_receipts: list[HistoricalReceiptPin] = Field(min_length=1, max_length=31)


class HistoricalPublishedCorrectionPin(PublishedEligibilityPin):
    product_version: Literal["v4"]
    lineage_receipts: list[HistoricalReceiptPin] = Field(min_length=1, max_length=31)
    parent_publication_response_digest: Digest


def historical_month_variant(value: Any) -> str:
    if isinstance(value, dict):
        return f"{value.get('product_version')}:{value.get('evidence_kind')}"
    return f"{getattr(value, 'product_version', None)}:{getattr(value, 'evidence_kind', None)}"


HistoricalMonthlyPin = Annotated[
    Annotated[HistoricalEvaluatedRootPin, Tag("v3:EVALUATED_ONLY")]
    | Annotated[HistoricalPublishedRootPin, Tag("v3:PUBLISHED")]
    | Annotated[HistoricalEvaluatedCorrectionPin, Tag("v4:EVALUATED_ONLY")]
    | Annotated[HistoricalPublishedCorrectionPin, Tag("v4:PUBLISHED")],
    Discriminator(historical_month_variant),
]


class HistoricalEligibilitySelection(BaseModel):
    """Exact new monthly authority; never implicitly upgrades a frozen selector."""

    model_config = ConfigDict(extra="forbid")
    selection_version: Literal["v3"]
    tenant_id: Identifier
    composite_id: Identifier
    definition_version: Identifier
    reporting_currency: str = Field(pattern=r"^[A-Z]{3}$")
    period_start: date
    period_end: date
    months: list[HistoricalMonthlyPin] = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def require_ordered_months(self) -> Self:
        plain = self.model_dump(mode="json", exclude={"selection_version"})
        for month in plain["months"]:
            month.pop("product_version")
            receipts = month.pop("lineage_receipts", [])
            month.pop("parent_publication_response_digest", None)
            if receipts and (
                receipts[-1]["product_version"] != "v3"
                or any(row["product_version"] != "v4" for row in receipts[:-1])
            ):
                raise ValueError("Historical corrections require one v3 original root")
        EligibilitySelection.model_validate(plain)
        return self


class CompositeReportIdentityV7(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["composite_review.v7"]
    qualification: Literal["CONTROLLED_HISTORICAL_POLICY_EVIDENCE_REPLAY"]
    publication_state: Literal["NOT_ATTESTED"]
    calculation_boundary: Literal[
        "Configured-identity controlled producer custody only; no cryptographic or bank provenance acceptance, TWR, MWR, dispersion, contribution or model-fee calculation. CONTROLLED / NOT_ATTESTED."
    ]
    selection: HistoricalEligibilitySelection
    series_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_revision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    factual_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
