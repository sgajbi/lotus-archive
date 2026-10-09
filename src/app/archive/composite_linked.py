"""Report-owned linked-analysis pins, retained without calculation authority."""

from datetime import date, timedelta
from typing import Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.archive.composite_identity import CompositeWindowPin, Digest, Identifier


class CompositeLinkedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_id: Literal["LINKED_MEMBER_CONTRIBUTION"]
    method: Literal["CARINO:v1"]
    composite_id: Identifier
    calculation_id: UUID
    period_start: date
    period_end: date
    return_view: Literal["GROSS", "NET_ACTUAL", "NET_MODEL_FEE"]
    reporting_currency: str = Field(pattern=r"^[A-Z]{3}$")
    materialization_ids: list[UUID] = Field(min_length=1, max_length=120)


class CompositeLinkedRequestWithNullSequence(CompositeLinkedRequest):
    """Explicit null remains distinct from an absent source-request field.

    Two strict wire shapes avoid inserting defaults or erasing output schema
    fields through a custom serializer. A competing numeric sequence is refused.
    """

    restatement_sequence: None


class CompositeLinkedSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: Identifier
    source_request: CompositeLinkedRequest | CompositeLinkedRequestWithNullSequence
    windows: list[CompositeWindowPin] = Field(min_length=1, max_length=120)
    engine_version: Identifier
    calculation_fingerprint: Digest
    response_digest: Digest

    @model_validator(mode="after")
    def exact_linked_vector(self) -> Self:
        ids = [window.materialization_id for window in self.windows]
        if len(set(ids)) != len(ids) or ids != self.source_request.materialization_ids:
            raise ValueError("linked request must name the exact unique ordered window vector")
        if (self.windows[0].period_start, self.windows[-1].period_end) != (
            self.source_request.period_start,
            self.source_request.period_end,
        ):
            raise ValueError("linked pins must cover the exact requested horizon")
        for previous, current in zip(self.windows, self.windows[1:]):
            if current.period_start != previous.period_end + timedelta(days=1):
                raise ValueError("linked pins must be chronological and contiguous")
        return self


class CompositeReportIdentityV3(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["composite_review.v3"]
    qualification: Literal["EXPLICIT_RETAINED_CALCULATED_REPLAY"]
    publication_state: Literal["NOT_ATTESTED"]
    selection: CompositeLinkedSelection
    series_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_revision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    factual_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
