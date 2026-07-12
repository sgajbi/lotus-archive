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
