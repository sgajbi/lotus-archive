from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import InMemoryAccessAuditRepository
from app.archive.authorization import ArchiveAuthorizationPolicy, AuthorizationFailedError
from app.archive.commands import LegalHoldCreateCommand
from app.archive.idea_lifecycle_decisions.models import (
    IdeaLifecycleDecision,
    IdeaLifecycleDecisionRequest,
)
from app.archive.idea_lifecycle_decisions.repository import (
    LifecycleDecisionConflictError,
    SqliteIdeaLifecycleDecisionRepository,
)
from app.archive.idea_lifecycle_decisions.service import (
    IdeaLifecycleDecisionService,
    LifecycleDecisionTenantError,
)
from app.archive.idea_lifecycle_decisions.signing import (
    Ed25519LifecycleDecisionSigner,
    verify_lifecycle_decision,
)
from app.archive.repository import InMemoryArchiveDocumentRepository
from app.archive.service import ArchiveDocumentService
from app.archive.storage import FilesystemObjectStorage
from app.security.caller_context import CallerContext
from tests.unit.test_archive_writer import valid_metadata_input

PRIVATE_KEY = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
PUBLIC_KEY = PRIVATE_KEY.public_key()


def test_issues_verifiable_short_lived_archive_owned_decision(tmp_path: Path) -> None:
    archive, document_id, audit = _archive(tmp_path)
    service = _decision_service(tmp_path, archive, audit)
    issued_at = datetime(2026, 7, 12, 1, 0, tzinfo=UTC)

    decision = service.issue(
        document_id=document_id,
        request=_request(),
        idempotency_key="decision-key-001",
        caller_context=_idea_context(),
        trace_id="trace-decision-001",
        issued_at_utc=issued_at,
    )

    assert decision.authority == "lotus-archive"
    assert decision.lifecycle_action == "RETAIN"
    assert decision.disposal_authorized is False
    assert decision.tenant_id == "tenant-private-bank"
    assert decision.payload_digest.startswith("sha256:")
    assert decision.signature.startswith("ed25519:")
    assert verify_lifecycle_decision(
        decision,
        trusted_keys={"archive-local-v1": PUBLIC_KEY},
        at_utc=issued_at + timedelta(minutes=1),
    )
    assert audit.list_by_document_id(document_id)[-1].event_type == ("idea_lifecycle_decision_read")


def test_verification_rejects_forged_expired_and_unknown_key_decisions(tmp_path: Path) -> None:
    archive, document_id, audit = _archive(tmp_path)
    issued_at = datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
    decision = _decision_service(tmp_path, archive, audit).issue(
        document_id=document_id,
        request=_request(),
        idempotency_key="decision-key-verification",
        caller_context=_idea_context(),
        trace_id="trace-decision-verification",
        issued_at_utc=issued_at,
    )

    forged = decision.model_copy(update={"idea_candidate_id": "icand_forged"})

    assert not verify_lifecycle_decision(
        forged,
        trusted_keys={"archive-local-v1": PUBLIC_KEY},
        at_utc=issued_at + timedelta(minutes=1),
    )
    assert not verify_lifecycle_decision(
        decision,
        trusted_keys={"archive-local-v1": PUBLIC_KEY},
        at_utc=decision.expires_at_utc,
    )
    assert not verify_lifecycle_decision(
        decision,
        trusted_keys={"unknown": PUBLIC_KEY},
        at_utc=issued_at + timedelta(minutes=1),
    )
    malformed = decision.model_copy(update={"signature": "ed25519:not-valid-base64%%%"})
    assert not verify_lifecycle_decision(
        malformed,
        trusted_keys={"archive-local-v1": PUBLIC_KEY},
        at_utc=issued_at + timedelta(minutes=1),
    )


def test_legal_hold_takes_precedence_over_elapsed_retention(tmp_path: Path) -> None:
    archive, document_id, audit = _archive(
        tmp_path,
        retention_start_date="2019-01-01",
        retain_until_date="2020-01-01",
    )
    archive.set_legal_hold(
        document_id=document_id,
        command=_hold_command(),
        caller_context=_report_context(),
        trace_id="trace-hold",
    )

    decision = _decision_service(tmp_path, archive, audit).issue(
        document_id=document_id,
        request=_request(),
        idempotency_key="decision-key-hold",
        caller_context=_idea_context(),
        trace_id="trace-decision-hold",
    )

    assert decision.lifecycle_action == "LEGAL_HOLD"
    assert decision.decision_reason_code == "legal_hold_active"
    assert decision.legal_hold_count == 1
    assert decision.disposal_authorized is False


def test_elapsed_retention_reports_eligibility_without_authorizing_disposal(
    tmp_path: Path,
) -> None:
    archive, document_id, audit = _archive(
        tmp_path,
        retention_start_date="2019-01-01",
        retain_until_date="2020-01-01",
    )

    decision = _decision_service(tmp_path, archive, audit).issue(
        document_id=document_id,
        request=_request(),
        idempotency_key="decision-key-eligible",
        caller_context=_idea_context(),
        trace_id="trace-decision-eligible",
    )

    assert decision.lifecycle_action == "DISPOSAL_ELIGIBLE"
    assert decision.decision_reason_code == "retention_elapsed"
    assert decision.disposal_authorized is False


def test_purged_document_reports_executed_disposal_without_new_authority(
    tmp_path: Path,
) -> None:
    archive, document_id, audit = _archive(
        tmp_path,
        retention_start_date="2019-01-01",
        retain_until_date="2020-01-01",
    )
    archive.purge_document(
        document_id=document_id,
        caller_context=_report_context(),
        trace_id="trace-purge-before-decision",
    )

    decision = _decision_service(tmp_path, archive, audit).issue(
        document_id=document_id,
        request=_request(),
        idempotency_key="decision-key-purged",
        caller_context=_idea_context(),
        trace_id="trace-decision-purged",
    )

    assert decision.lifecycle_action == "DISPOSAL_EXECUTED"
    assert decision.decision_reason_code == "purge_executed"
    assert decision.disposal_authorized is False


@pytest.mark.parametrize(
    "metadata_overrides",
    [
        {"report_type": "portfolio_review", "template_id": "portfolio-review"},
        {"retention_policy_id": None},
    ],
)
def test_non_idea_document_posture_is_rejected(
    tmp_path: Path,
    metadata_overrides: dict[str, object],
) -> None:
    archive, document_id, audit = _archive(tmp_path, **metadata_overrides)

    with pytest.raises(ValueError):
        _decision_service(tmp_path, archive, audit).issue(
            document_id=document_id,
            request=_request(),
            idempotency_key="decision-key-invalid-document",
            caller_context=_idea_context(),
            trace_id="trace-invalid-document",
        )


def test_replay_survives_fresh_repository_and_changed_input_conflicts(tmp_path: Path) -> None:
    archive, document_id, audit = _archive(tmp_path)
    first_service = _decision_service(tmp_path, archive, audit)
    first = first_service.issue(
        document_id=document_id,
        request=_request(),
        idempotency_key="decision-key-restart",
        caller_context=_idea_context(),
        trace_id="trace-first",
    )
    restarted = _decision_service(tmp_path, archive, audit)

    replay = restarted.issue(
        document_id=document_id,
        request=_request(),
        idempotency_key="decision-key-restart",
        caller_context=_idea_context(),
        trace_id="trace-replay",
    )

    assert replay == first
    with pytest.raises(LifecycleDecisionConflictError):
        restarted.issue(
            document_id=document_id,
            request=_request(idea_candidate_id="icand_changed"),
            idempotency_key="decision-key-restart",
            caller_context=_idea_context(),
            trace_id="trace-conflict",
        )


def test_repository_insert_race_replays_or_conflicts_and_rolls_back(tmp_path: Path) -> None:
    archive, document_id, audit = _archive(tmp_path)
    service = _decision_service(tmp_path, archive, audit)
    decision = service.issue(
        document_id=document_id,
        request=_request(),
        idempotency_key="decision-key-race-source",
        caller_context=_idea_context(),
        trace_id="trace-race-source",
    )
    repository = SqliteIdeaLifecycleDecisionRepository(tmp_path / "race.sqlite3")
    repository.save(
        idempotency_key="decision-key-race",
        request_fingerprint="sha256:first",
        decision=decision,
    )

    replay = repository.save(
        idempotency_key="decision-key-race",
        request_fingerprint="sha256:first",
        decision=decision,
    )
    assert replay == decision
    with pytest.raises(LifecycleDecisionConflictError):
        repository.save(
            idempotency_key="decision-key-race",
            request_fingerprint="sha256:changed",
            decision=decision,
        )
    with pytest.raises(RuntimeError, match="rollback"):
        with repository._connect() as connection:  # noqa: SLF001 - transaction regression proof
            connection.execute("DELETE FROM idea_lifecycle_decision")
            raise RuntimeError("rollback")
    assert repository.get("decision-key-race") is not None


def test_tenant_and_service_authority_fail_closed(tmp_path: Path) -> None:
    archive, document_id, audit = _archive(tmp_path)
    service = _decision_service(tmp_path, archive, audit)

    with pytest.raises(LifecycleDecisionTenantError):
        service.issue(
            document_id=document_id,
            request=_request(),
            idempotency_key="decision-key-wrong-tenant",
            caller_context=_idea_context(tenant_id="tenant-other"),
            trace_id="trace-wrong-tenant",
        )


def test_repository_failure_does_not_emit_success_audit_event(tmp_path: Path) -> None:
    archive, document_id, audit = _archive(tmp_path)
    service = IdeaLifecycleDecisionService(
        posture_reader=archive,
        repository=_FailingDecisionRepository(),
        signer=Ed25519LifecycleDecisionSigner(
            private_key=PRIVATE_KEY,
            key_id="archive-local-v1",
        ),
        authorization_policy=ArchiveAuthorizationPolicy(),
        audit_repository=audit,
    )

    with pytest.raises(RuntimeError, match="decision persistence unavailable"):
        service.issue(
            document_id=document_id,
            request=_request(),
            idempotency_key="decision-key-storage-failure",
            caller_context=_idea_context(),
            trace_id="trace-storage-failure",
        )

    assert all(
        event.event_type != "idea_lifecycle_decision_read"
        for event in audit.list_by_document_id(document_id)
    )
    with pytest.raises(AuthorizationFailedError):
        service.issue(
            document_id=document_id,
            request=_request(),
            idempotency_key="decision-key-unauthorized",
            caller_context=_idea_context(caller_service="unapproved-service"),
            trace_id="trace-unauthorized",
        )


def _archive(
    tmp_path: Path,
    **metadata_overrides: object,
) -> tuple[ArchiveDocumentService, str, InMemoryAccessAuditRepository]:
    repository = InMemoryArchiveDocumentRepository()
    storage = FilesystemObjectStorage(tmp_path / "objects")
    audit = InMemoryAccessAuditRepository()
    archive = ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=audit,
    )
    metadata_values = {
        "report_type": "proof_pack",
        "template_id": "proof-pack",
        **metadata_overrides,
    }
    metadata = archive.writer.archive_document(
        metadata_input=valid_metadata_input(**metadata_values),
        content=b"idea evidence proof pack",
    )
    return archive, metadata.document_id, audit


def _decision_service(
    tmp_path: Path,
    archive: ArchiveDocumentService,
    audit: InMemoryAccessAuditRepository,
) -> IdeaLifecycleDecisionService:
    return IdeaLifecycleDecisionService(
        posture_reader=archive,
        repository=SqliteIdeaLifecycleDecisionRepository(tmp_path / "decisions.sqlite3"),
        signer=Ed25519LifecycleDecisionSigner(
            private_key=PRIVATE_KEY,
            key_id="archive-local-v1",
        ),
        authorization_policy=ArchiveAuthorizationPolicy(),
        audit_repository=audit,
    )


def _request(**overrides: str) -> IdeaLifecycleDecisionRequest:
    values = {
        "idea_evidence_pack_id": "irep_001",
        "idea_candidate_id": "icand_001",
        "source_correlation_ref": "corr-idea-001",
        **overrides,
    }
    return IdeaLifecycleDecisionRequest.model_validate(values)


def _idea_context(
    *,
    tenant_id: str | None = "tenant-private-bank",
    caller_service: str = "lotus-idea",
) -> CallerContext:
    return CallerContext(
        caller_service=caller_service,
        actor_type="service",
        actor_id="idea-lifecycle-worker",
        correlation_id="corr-decision-001",
        tenant_id=tenant_id,
    )


def _report_context() -> CallerContext:
    return CallerContext(
        caller_service="lotus-report",
        actor_type="service",
        actor_id="report-worker",
        correlation_id="corr-hold-001",
        tenant_id="tenant-private-bank",
    )


class _FailingDecisionRepository:
    def get(self, idempotency_key: str) -> None:
        return None

    def save(
        self,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        decision: IdeaLifecycleDecision,
    ) -> IdeaLifecycleDecision:
        raise RuntimeError("decision persistence unavailable")


def _hold_command() -> LegalHoldCreateCommand:
    return LegalHoldCreateCommand(
        hold_reason="Regulatory inquiry",
        authority_reference="LEGAL-2026-001",
    )
