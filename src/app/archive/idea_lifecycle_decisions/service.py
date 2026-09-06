from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Protocol, Sequence

from app.archive.audit import (
    AccessAuditRepository,
    AccessEventType,
    AuthorizationDecision,
    access_audit_event,
)
from app.archive.authorization import ArchiveAuthorizationPolicy, ArchivePermission
from app.archive.idea_lifecycle_decisions.models import (
    LifecycleVerificationKey,
    IdeaLifecycleAction,
    IdeaLifecycleDecision,
    IdeaLifecycleDecisionRequest,
)
from app.archive.idea_lifecycle_decisions.repository import (
    IdeaLifecycleDecisionRepository,
    LifecycleDecisionConflictError,
)
from app.archive.idea_lifecycle_decisions.signing import (
    LifecycleDecisionSigner,
    RetiredVerificationKey,
)
from app.archive.models import ArchiveDocumentMetadata, LegalHoldStatus, PurgeStatus
from app.security.caller_context import CallerContext


#: Stand-in start for an ephemeral development key, which has no provisioned
#: window. Only reachable in the local profile: settings refuse to start
#: elsewhere without a real one, so this never labels a production key.
_EPHEMERAL_KEY_START = datetime(1970, 1, 1, tzinfo=UTC)


class LifecycleDecisionTenantError(PermissionError):
    pass


class LifecycleDecisionDocumentError(ValueError):
    pass


class ArchiveLifecyclePostureReader(Protocol):
    def get_lifecycle_posture(self, document_id: str) -> ArchiveDocumentMetadata: ...


class IdeaLifecycleDecisionService:
    def __init__(
        self,
        *,
        posture_reader: ArchiveLifecyclePostureReader,
        repository: IdeaLifecycleDecisionRepository,
        signer: LifecycleDecisionSigner,
        authorization_policy: ArchiveAuthorizationPolicy,
        audit_repository: AccessAuditRepository,
        decision_ttl: timedelta = timedelta(minutes=5),
        signing_key_not_before_utc: datetime | None = None,
        retired_verification_keys: Sequence[RetiredVerificationKey] = (),
    ) -> None:
        self._posture_reader = posture_reader
        self._repository = repository
        self._signer = signer
        self._signing_key_not_before_utc = signing_key_not_before_utc
        self._retired_verification_keys = tuple(retired_verification_keys)
        self._authorization_policy = authorization_policy
        self._audit_repository = audit_repository
        self._decision_ttl = decision_ttl

    def verification_keys(self) -> list[LifecycleVerificationKey]:
        """Every key a consumer needs to verify decisions this service issued.

        The active signer plus every retained key. A list alone was not enough:
        while only the active signer was published, rotating dropped the key
        that signed every earlier decision, and those decisions stopped
        verifying for any consumer building trust from this document.

        Each key carries the window it signed in, because a consumer selects a
        key by the decision's issue time. The active key's start is provisioned
        configuration and is never defaulted -- a guessed window either keeps a
        retired key trusted forever or makes real decisions unverifiable.

        `provenance` is `managed` or `ephemeral_development`, and reports where
        the key material came from, not that it is well custodied. A consumer
        must refuse an ephemeral key: it is regenerated per process, so a
        decision signed under it cannot be verified after a restart.
        """
        key_id = self._signer.key_id
        active = LifecycleVerificationKey(
            key_id=key_id,
            algorithm="ed25519",
            public_key_base64=self._signer.public_key_base64(),
            provenance=(
                "ephemeral_development" if key_id.startswith("ephemeral-local") else "managed"
            ),
            status="active",
            not_before_utc=self._signing_key_not_before_utc or _EPHEMERAL_KEY_START,
            not_after_utc=None,
        )
        retired = [
            LifecycleVerificationKey(
                key_id=key.key_id,
                algorithm="ed25519",
                public_key_base64=key.public_key_base64,
                # Retained keys are provisioned, so they are managed by
                # construction: an ephemeral key cannot outlive the process
                # that generated it and can never be carried forward.
                provenance="managed",
                status="retired",
                not_before_utc=key.not_before_utc,
                not_after_utc=key.not_after_utc,
            )
            for key in self._retired_verification_keys
        ]
        return [active, *retired]

    def issue(
        self,
        *,
        document_id: str,
        request: IdeaLifecycleDecisionRequest,
        idempotency_key: str,
        caller_context: CallerContext,
        trace_id: str,
        issued_at_utc: datetime | None = None,
    ) -> IdeaLifecycleDecision:
        self._authorization_policy.authorize(
            permission=ArchivePermission.READ_IDEA_LIFECYCLE_DECISION,
            caller_context=caller_context,
            audit_repository=self._audit_repository,
            trace_id=trace_id,
            document_id=document_id,
        )
        if caller_context.tenant_id is None:
            raise LifecycleDecisionTenantError("tenant context is required")
        fingerprint = _request_fingerprint(
            document_id=document_id,
            request=request,
            tenant_id=caller_context.tenant_id,
        )
        existing = self._repository.get(idempotency_key)
        if existing is not None:
            if existing[0] != fingerprint:
                raise LifecycleDecisionConflictError(
                    "idempotency key was reused with different lifecycle decision input"
                )
            return existing[1]

        metadata = self._posture_reader.get_lifecycle_posture(document_id)
        if metadata.tenant_id is None or metadata.tenant_id != caller_context.tenant_id:
            raise LifecycleDecisionTenantError("document tenant does not match caller tenant")
        if metadata.report_type.value != "proof_pack":
            raise LifecycleDecisionDocumentError(
                "Idea lifecycle decisions require an archived proof-pack document"
            )
        if metadata.retention_policy_id is None:
            raise LifecycleDecisionDocumentError("document has no retention policy")

        issued_at = issued_at_utc or datetime.now(UTC)
        action, reason = _decision_action(metadata)
        unsigned = {
            "contract_version": "lotus-archive:IdeaEvidenceLifecycleDecision:v1",
            "decision_id": _decision_id(idempotency_key, fingerprint),
            "document_id": document_id,
            "idea_evidence_pack_id": request.idea_evidence_pack_id,
            "idea_candidate_id": request.idea_candidate_id,
            "source_correlation_ref": request.source_correlation_ref,
            "tenant_id": caller_context.tenant_id,
            "residency_region": metadata.region,
            "retention_policy_id": metadata.retention_policy_id,
            "legal_hold_status": metadata.legal_hold_status,
            "legal_hold_count": metadata.legal_hold_count,
            "purge_status": metadata.purge_status,
            "lifecycle_action": action,
            "disposal_authorized": False,
            "decision_reason_code": reason,
            "authority": "lotus-archive",
            "issued_at_utc": issued_at,
            "expires_at_utc": issued_at + self._decision_ttl,
            "correlation_id": caller_context.correlation_id,
            "trace_id": trace_id,
            "signing_algorithm": "Ed25519",
            "signing_key_id": self._signer.key_id,
        }
        signable = IdeaLifecycleDecision.model_validate(
            {**unsigned, "payload_digest": "sha256:pending", "signature": "ed25519:pending"}
        ).model_dump(mode="json", exclude={"payload_digest", "signature"})
        digest, signature = self._signer.sign(signable)
        decision = IdeaLifecycleDecision.model_validate(
            {**unsigned, "payload_digest": digest, "signature": signature}
        )
        stored = self._repository.save(
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            decision=decision,
        )
        self._audit_repository.record(
            access_audit_event(
                event_type=AccessEventType.IDEA_LIFECYCLE_DECISION_READ,
                caller_context=caller_context,
                trace_id=trace_id,
                authorization_decision=AuthorizationDecision.ALLOWED,
                authorization_reason_code="idea_lifecycle_decision_read_allowed",
                operation_reason_code=stored.decision_reason_code,
                document_id=document_id,
            )
        )
        return stored


def _decision_action(metadata: ArchiveDocumentMetadata) -> tuple[IdeaLifecycleAction, str]:
    if metadata.legal_hold_status is LegalHoldStatus.ACTIVE:
        return IdeaLifecycleAction.LEGAL_HOLD, "legal_hold_active"
    if metadata.purge_status is PurgeStatus.PURGED:
        return IdeaLifecycleAction.DISPOSAL_EXECUTED, "purge_executed"
    if metadata.purge_status is PurgeStatus.ELIGIBLE:
        return IdeaLifecycleAction.DISPOSAL_ELIGIBLE, "retention_elapsed"
    return IdeaLifecycleAction.RETAIN, "retention_period_active"


def _request_fingerprint(
    *,
    document_id: str,
    request: IdeaLifecycleDecisionRequest,
    tenant_id: str,
) -> str:
    payload = {
        "document_id": document_id,
        "request": request.model_dump(mode="json"),
        "tenant_id": tenant_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _decision_id(idempotency_key: str, fingerprint: str) -> str:
    digest = hashlib.sha256(f"{idempotency_key}:{fingerprint}".encode()).hexdigest()
    return "archive_lifecycle_decision_" + digest[:24]
