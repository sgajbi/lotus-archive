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
    #: Uppercase region code, matching what `lotus-idea` accepts. Its
    #: `archive_posture.py` refuses anything else at contract mapping, before
    #: verification, so an unconstrained value here becomes a decision the
    #: consumer cannot read -- failing at their end with nothing naming this
    #: service. Real documents carry values like `SG`, so this enforces current
    #: behaviour rather than changing it.
    residency_region: str = Field(pattern=r"^[A-Z]{2,16}$")
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


class LifecycleKeyStatus(StrEnum):
    """The governed lifecycle key-status vocabulary.

    Constrained rather than a free `str` because the previous field accepted
    anything: a typo, an empty string and `definitely-not-valid` were all
    publishable and all verified identically, since nothing read the value.

    `rotated` and `revoked` are not two names for the same thing, and the
    difference is what a consumer acts on. A **rotated** key stopped signing and
    keeps verifying inside its closed window -- that is what retention exists
    for. A **revoked** key verifies nothing at any instant, including inside the
    window it really did sign in, because the claim being withdrawn is that its
    signatures ever meant anything. Both stay published; removing a revoked key
    instead would answer "this key was never ours" for a key that was, which is
    the one distinction this bundle exists to preserve.
    """

    ACTIVE = "active"
    ROTATED = "rotated"
    REVOKED = "revoked"


class LifecycleVerificationKey(BaseModel):
    """A key a consumer can use to verify a lifecycle decision Archive issued."""

    key_id: str = Field(description="Matches `signing_key_id` on a decision.")
    algorithm: str = Field(description="Signature algorithm; `ed25519` today.")
    public_key_base64: str = Field(description="Raw 32-byte Ed25519 public key, base64url-encoded.")
    status: LifecycleKeyStatus = Field(
        description=(
            "`active` for the key currently signing, `rotated` for one retained so "
            "decisions it signed stay verifiable, or `revoked` for one whose "
            "signatures are withdrawn. `active` and `rotated` verify inside their "
            "windows; `revoked` verifies at no instant. Only `active` signs."
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
    """Every key a consumer needs to reach a verdict, including revoked ones.

    Not "every acceptable key": a revoked entry is published precisely so a
    consumer can refuse decisions it signed, and dropping it would make a
    withdrawn key indistinguishable from one that was never Archive's.

    A list rather than one key so a rotation publishes the incoming key
    alongside the outgoing one, instead of forcing every consumer to cut over
    at the instant of rotation. The list shape alone was not enough: until
    rotated keys were retained here, rotation silently dropped the key that
    signed every earlier decision.
    """

    keys: list[LifecycleVerificationKey]
