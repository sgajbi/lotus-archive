"""Strict Report-owned definition and membership pins; no source reconstruction."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.archive.composite_identity import Digest, Identifier


class CompositeDefinitionPin(BaseModel):
    """Exact original Manage v1 definition; the caller cannot supply inception."""

    model_config = ConfigDict(extra="forbid")
    definition_version: Identifier
    content_hash: Digest
    response_digest: Digest


class CompositeMembershipPin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    membership_revision: Identifier
    content_hash: Digest
    response_digest: Digest


class CompositeSourceContextSelection(BaseModel):
    """Shared definition custody with explicitly selected optional attachments."""

    model_config = ConfigDict(extra="forbid")
    definition: CompositeDefinitionPin
    since_inception: bool = Field(default=False, strict=True)
    memberships: list[CompositeMembershipPin] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def require_attachment(self) -> Self:
        if not self.since_inception and not self.memberships:
            raise ValueError("source context requires an explicitly selected attachment")
        if len({pin.membership_revision for pin in self.memberships}) != len(self.memberships):
            raise ValueError("source context membership revisions must be unique")
        return self


class CompositeDefinitionCustody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pin: CompositeDefinitionPin
    source_response_digest: Digest

    @model_validator(mode="after")
    def response_digest_agrees(self) -> Self:
        if self.source_response_digest != self.pin.response_digest:
            raise ValueError("definition response digest must match its exact pin")
        return self
