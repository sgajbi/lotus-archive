"""Report-owned composite pins preserved by Archive without financial authority."""

from datetime import date, timedelta
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^\S+$")]


class CompositeWindowPin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    materialization_id: UUID
    period_start: date
    period_end: date
    restatement_sequence: int = Field(ge=1, strict=True)
    definition_content_hash: Digest
    membership_content_hash: Digest
    attestation_content_hash: Digest
    source_cut_id: Identifier
    method_binding: dict[str, str] = Field(min_length=1)
    retained_receipt_fingerprint: Digest

    @model_validator(mode="after")
    def ordered_window(self) -> Self:
        if self.period_end < self.period_start:
            raise ValueError("composite window ends before it starts")
        if any(not key.strip() or not value.strip() for key, value in self.method_binding.items()):
            raise ValueError("method binding requires nonblank source identity")
        return self


class CompositeSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: Identifier
    composite_id: Identifier
    calculation_id: UUID
    period_start: date
    period_end: date
    reporting_currency: str = Field(pattern=r"^[A-Z]{3}$")
    return_view: Literal["GROSS", "NET_ACTUAL", "NET_MODEL_FEE"]
    methodology: Identifier
    engine_version: Identifier
    calculation_fingerprint: Digest
    response_digest: Digest
    windows: list[CompositeWindowPin] = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def ordered_vector(self) -> Self:
        if len({pin.materialization_id for pin in self.windows}) != len(self.windows):
            raise ValueError("composite materialization identities must be unique")
        if (self.windows[0].period_start, self.windows[-1].period_end) != (
            self.period_start,
            self.period_end,
        ):
            raise ValueError("composite pins must cover the exact report horizon")
        for previous, current in zip(self.windows, self.windows[1:]):
            if current.period_start != previous.period_end + timedelta(days=1):
                raise ValueError("composite pins must be chronological and contiguous")
        return self


class CompositeReportIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["composite_review.v1"]
    qualification: Literal["EXPLICIT_RETAINED_CALCULATED_REPLAY"]
    publication_state: Literal["NOT_ATTESTED"]
    selection: CompositeSelection
    series_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_revision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    factual_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
