from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.archive.models import LegalHoldStatus, PurgeStatus


class IdeaLifecycleAction(StrEnum):
    RETAIN = "RETAIN"
    LEGAL_HOLD = "LEGAL_HOLD"
    DISPOSAL_ELIGIBLE = "DISPOSAL_ELIGIBLE"
    DISPOSAL_EXECUTED = "DISPOSAL_EXECUTED"


class IdeaLifecycleDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    idea_evidence_pack_id: str = Field(min_length=3)
    idea_candidate_id: str = Field(min_length=3)
    source_correlation_ref: str = Field(min_length=3)


class IdeaLifecycleDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["lotus-archive:IdeaEvidenceLifecycleDecision:v1"]
    decision_id: str
    document_id: str
    idea_evidence_pack_id: str
    idea_candidate_id: str
    source_correlation_ref: str
    tenant_id: str
    residency_region: str
    retention_policy_id: str
    legal_hold_status: LegalHoldStatus
    legal_hold_count: int
    purge_status: PurgeStatus
    lifecycle_action: IdeaLifecycleAction
    disposal_authorized: Literal[False]
    decision_reason_code: str
    authority: Literal["lotus-archive"]
    issued_at_utc: datetime
    expires_at_utc: datetime
    correlation_id: str
    trace_id: str
    signing_algorithm: Literal["Ed25519"]
    signing_key_id: str
    payload_digest: str
    signature: str


class LifecycleVerificationKey(BaseModel):
    """A key a consumer can use to verify a lifecycle decision Archive issued."""

    key_id: str = Field(description="Matches `signing_key_id` on a decision.")
    algorithm: str = Field(description="Signature algorithm; `ed25519` today.")
    public_key_base64: str = Field(description="Raw 32-byte Ed25519 public key, base64url-encoded.")
    status: str = Field(
        description=(
            "`active` for the key currently signing, or `retired` for one retained so "
            "decisions it signed stay verifiable. Both are acceptable for verification; "
            "only `active` signs."
        )
    )
    not_before_utc: datetime = Field(
        description=(
            "Start of the window this key signed in. A consumer selects a key by the "
            "decision's issue time, so this is required to verify a historical decision "
            "after a rotation. Provisioned, never defaulted."
        )
    )
    not_after_utc: datetime | None = Field(
        default=None,
        description=(
            "End of the window, or null while the key is still signing. A decision "
            "issued after this instant was not signed by this key."
        ),
    )
    provenance: str = Field(
        description=(
            "`managed` for provisioned key material, or `ephemeral_development` for a key "
            "generated per process in the local profile. A consumer MUST refuse an "
            "ephemeral key: decisions signed under it cannot be verified after a restart."
        )
    )


class LifecycleVerificationKeys(BaseModel):
    """Every key currently acceptable for verification, active and retired.

    A list rather than one key so a rotation publishes the incoming key
    alongside the outgoing one, instead of forcing every consumer to cut over
    at the instant of rotation. The list shape alone was not enough: until
    retired keys were retained here, rotation silently dropped the key that
    signed every earlier decision.
    """

    keys: list[LifecycleVerificationKey]
