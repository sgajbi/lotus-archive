from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.archive.api import idea_lifecycle_decision_service
from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import InMemoryAccessAuditRepository
from app.archive.authorization import ArchiveAuthorizationPolicy
from app.archive.idea_lifecycle_decisions.repository import SqliteIdeaLifecycleDecisionRepository
from app.archive.idea_lifecycle_decisions.service import IdeaLifecycleDecisionService
from app.archive.idea_lifecycle_decisions.signing import Ed25519LifecycleDecisionSigner
from app.archive.repository import InMemoryArchiveDocumentRepository
from app.archive.service import ArchiveDocumentService
from app.archive.storage import FilesystemObjectStorage
from app.main import app
from tests.unit.test_archive_writer import valid_metadata_input


def test_api_issues_and_replays_source_safe_authenticated_decision(tmp_path: Path) -> None:
    service, document_id = _services(tmp_path)
    app.dependency_overrides[idea_lifecycle_decision_service] = lambda: service
    client = TestClient(app)
    try:
        first = client.post(
            f"/documents/{document_id}/idea-lifecycle-decisions",
            json=_payload(),
            headers=_headers("decision-api-001"),
        )
        replay = client.post(
            f"/documents/{document_id}/idea-lifecycle-decisions",
            json=_payload(),
            headers=_headers("decision-api-001"),
        )
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json() == first.json()
    assert first.json()["authority"] == "lotus-archive"
    assert first.json()["disposal_authorized"] is False
    assert "portfolio_id" not in first.json()


def test_api_rejects_wrong_tenant_and_changed_replay(tmp_path: Path) -> None:
    service, document_id = _services(tmp_path)
    app.dependency_overrides[idea_lifecycle_decision_service] = lambda: service
    client = TestClient(app)
    try:
        wrong_tenant = client.post(
            f"/documents/{document_id}/idea-lifecycle-decisions",
            json=_payload(),
            headers={**_headers("decision-api-tenant"), "X-Tenant-Id": "tenant-other"},
        )
        accepted = client.post(
            f"/documents/{document_id}/idea-lifecycle-decisions",
            json=_payload(),
            headers=_headers("decision-api-conflict"),
        )
        conflict = client.post(
            f"/documents/{document_id}/idea-lifecycle-decisions",
            json={**_payload(), "idea_candidate_id": "icand_changed"},
            headers=_headers("decision-api-conflict"),
        )
    finally:
        app.dependency_overrides.clear()

    assert wrong_tenant.status_code == 403
    assert wrong_tenant.json()["error"]["code"] == "lifecycle_decision_tenant_forbidden"
    assert accepted.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "lifecycle_decision_idempotency_conflict"


def test_api_requires_idempotency_and_tenant_headers(tmp_path: Path) -> None:
    service, document_id = _services(tmp_path)
    app.dependency_overrides[idea_lifecycle_decision_service] = lambda: service
    client = TestClient(app)
    headers = _headers("unused")
    headers.pop("Idempotency-Key")
    headers.pop("X-Tenant-Id")
    try:
        missing_idempotency = client.post(
            f"/documents/{document_id}/idea-lifecycle-decisions",
            json=_payload(),
            headers=headers,
        )
        headers["Idempotency-Key"] = "decision-api-missing-tenant"
        missing_tenant = client.post(
            f"/documents/{document_id}/idea-lifecycle-decisions",
            json=_payload(),
            headers=headers,
        )
    finally:
        app.dependency_overrides.clear()

    assert missing_idempotency.status_code == 422
    assert missing_tenant.status_code == 403


def _services(tmp_path: Path) -> tuple[IdeaLifecycleDecisionService, str]:
    repository = InMemoryArchiveDocumentRepository()
    storage = FilesystemObjectStorage(tmp_path / "objects")
    audit = InMemoryAccessAuditRepository()
    archive = ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=audit,
    )
    metadata = archive.writer.archive_document(
        metadata_input=valid_metadata_input(report_type="proof_pack", template_id="proof-pack"),
        content=b"idea evidence proof pack",
    )
    return (
        IdeaLifecycleDecisionService(
            posture_reader=archive,
            repository=SqliteIdeaLifecycleDecisionRepository(tmp_path / "decisions.sqlite3"),
            signer=Ed25519LifecycleDecisionSigner(
                private_key=Ed25519PrivateKey.from_private_bytes(bytes(range(32))),
                key_id="archive-test-v1",
            ),
            authorization_policy=ArchiveAuthorizationPolicy(),
            audit_repository=audit,
        ),
        metadata.document_id,
    )


def _payload() -> dict[str, str]:
    return {
        "idea_evidence_pack_id": "irep_001",
        "idea_candidate_id": "icand_001",
        "source_correlation_ref": "corr-idea-001",
    }


def _headers(idempotency_key: str) -> dict[str, str]:
    return {
        "Idempotency-Key": idempotency_key,
        "X-Correlation-Id": "corr-decision-api",
        "X-Trace-Id": "trace-decision-api",
        "X-Caller-Service": "lotus-idea",
        "X-Actor-Type": "service",
        "X-Actor-Id": "idea-lifecycle-worker",
        "X-Tenant-Id": "tenant-private-bank",
    }
