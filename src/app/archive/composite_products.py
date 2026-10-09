"""Strict custody of Report's bounded source products; no return calculation."""

from calendar import monthrange
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.archive.composite_identity import CompositeReportIdentity, CompositeSelection, Digest
from app.archive.composite_linked import CompositeReportIdentityV3
from app.archive.composite_eligibility import CompositeReportIdentityV4

ProductKey = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]


def require_complete_months(selection: CompositeSelection) -> None:
    for window in selection.windows:
        start, end = window.period_start, window.period_end
        if (
            start.day != 1
            or (start.year, start.month) != (end.year, end.month)
            or end.day != monthrange(end.year, end.month)[1]
        ):
            raise ValueError("source products require complete calendar months")


class CalendarReturnPin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["CALENDAR_RETURN"]
    product_key: ProductKey
    year: int = Field(ge=1, le=9999, strict=True)
    selection: CompositeSelection

    @model_validator(mode="after")
    def calendar_horizon(self) -> Self:
        start, end = self.selection.period_start, self.selection.period_end
        if (start.year, start.month, start.day, end.year, end.month, end.day) != (
            self.year,
            1,
            1,
            self.year,
            12,
            31,
        ) or len(self.selection.windows) != 12:
            raise ValueError("calendar product must cover its complete named year")
        require_complete_months(self.selection)
        return self


class TrailingReturnPin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["TRAILING_RETURN"]
    product_key: ProductKey
    months: int = Field(ge=1, le=120, strict=True)
    selection: CompositeSelection

    @model_validator(mode="after")
    def trailing_horizon(self) -> Self:
        if len(self.selection.windows) != self.months:
            raise ValueError("trailing product must cover its named month count")
        require_complete_months(self.selection)
        return self


class CompositeSourceProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pin: Annotated[CalendarReturnPin | TrailingReturnPin, Field(discriminator="kind")]
    source_response_digest: Digest

    @model_validator(mode="after")
    def response_digest_agrees(self) -> Self:
        if self.source_response_digest != self.pin.selection.response_digest:
            raise ValueError("source product response digest must match its selection")
        return self


class CompositeReportIdentityV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["composite_review.v2"]
    qualification: Literal["EXPLICIT_RETAINED_CALCULATED_REPLAY"]
    publication_state: Literal["NOT_ATTESTED"]
    selection: CompositeSelection
    series_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_revision_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    factual_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_products: list[CompositeSourceProduct] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def product_scope(self) -> Self:
        keys = [product.pin.product_key for product in self.source_products]
        if len(set(keys)) != len(keys):
            raise ValueError("source product keys must be unique")
        scope = (
            "tenant_id",
            "composite_id",
            "reporting_currency",
            "return_view",
            "methodology",
            "engine_version",
        )
        for product in self.source_products:
            selection = product.pin.selection
            if any(getattr(selection, key) != getattr(self.selection, key) for key in scope):
                raise ValueError("source products must match primary calculation scope")
            expected = [
                window
                for window in self.selection.windows
                if window.period_start >= selection.period_start
                and window.period_end <= selection.period_end
            ]
            if selection.windows != expected:
                raise ValueError("source products must retain the exact primary window subvector")
            if isinstance(product.pin, TrailingReturnPin) and (
                selection.period_end != self.selection.period_end
            ):
                raise ValueError("trailing products must end at the primary horizon")
        return self


CompositeCustodyIdentity = Annotated[
    CompositeReportIdentity
    | CompositeReportIdentityV2
    | CompositeReportIdentityV3
    | CompositeReportIdentityV4,
    Field(discriminator="contract_version"),
]
