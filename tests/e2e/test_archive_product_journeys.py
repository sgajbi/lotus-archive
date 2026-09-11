"""Caller-visible Archive journeys through the assembled HTTP application.

These tests deliberately use PostgreSQL metadata/audit state and filesystem
object storage. The database requirement is enforced in CI; a workstation
without a disposable PostgreSQL instance reports an explicit skip.
"""

from __future__ import annotations

from base64 import b64encode
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.archive.idea_lifecycle_decisions.models import (
    IdeaLifecycleDecision,
    LifecycleVerificationKeys,
)
from app.archive.idea_lifecycle_decisions.signing import (
    refuse_lifecycle_decision_against_bundle,
)
from app.archive.settings import ArchiveRuntimeSettings
from app.archive.storage import FilesystemObjectStorage
from app.main import app
from tests.database_proof import required_database_url
from tests.unit.test_archive_metadata_model import idea_evidence_pack_summary
from tests.unit.test_archive_writer import valid_metadata_input

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def assembled_archive(tmp_path: Path) -> Iterator[TestClient]:
    database_url = required_database_url()
    with psycopg.connect(database_url, autocommit=True) as connection:
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            connection.execute(migration.read_text(encoding="utf-8"))
        connection.execute("TRUNCATE archive_access_audit")
        connection.execute(
            "TRUNCATE archive_lifecycle_relationships, archive_legal_holds, archive_documents"
        )

    _clear_runtime_services()
    app.state.archive_runtime_settings = ArchiveRuntimeSettings(
        runtime_profile="test",
        repository_mode="postgresql",
        database_url=database_url,
        storage_mode="filesystem",
        storage_root=tmp_path / "objects",
        storage_namespace="e2e",
        idea_lifecycle_decision_ledger_path=tmp_path / "lifecycle-decisions.sqlite3",
        idea_lifecycle_decision_private_key_base64=SecretStr(
            b64encode(bytes(range(32))).decode("ascii")
        ),
        idea_lifecycle_decision_signing_key_id="archive-e2e-managed-v1",
        idea_lifecycle_decision_signing_key_not_before_utc=datetime(2026, 1, 1, tzinfo=UTC),
    )
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    client.close()
    _clear_runtime_services()


def test_archive_and_read_back_bytes_checksum_and_metadata(
    assembled_archive: TestClient,
) -> None:
    content = b"governed portfolio review"
    created = assembled_archive.post(
        "/documents",
        json=_document_payload("read-back", content=content),
        headers=_headers("lotus-render", "read-back-create"),
    )

    assert created.status_code == 201
    document_id = created.json()["document_id"]
    expected_checksum = sha256(content).hexdigest()
    assert created.json()["checksum"] == expected_checksum

    metadata = assembled_archive.get(
        f"/documents/{document_id}",
        headers=_headers("lotus-gateway", "read-back-metadata"),
    )
    download = assembled_archive.get(
        f"/documents/{document_id}/download",
        headers=_headers("lotus-gateway", "read-back-download"),
    )

    assert metadata.status_code == 200
    assert metadata.json()["checksum"] == expected_checksum
    assert metadata.json()["archive_request_id"] == "archive-request-read-back"
    assert download.status_code == 200
    assert download.content == content
    assert download.headers["X-Document-Checksum"] == expected_checksum
    assert download.headers["X-Document-Checksum-Algorithm"] == "sha256"


def test_hold_refusal_release_purge_and_post_purge_denial(
    assembled_archive: TestClient,
) -> None:
    document_id = _archive_expired_document(assembled_archive, "hold-purge")
    hold = assembled_archive.post(
        f"/documents/{document_id}/legal-holds",
        json={"hold_reason": "Regulatory review", "authority_reference": "CASE-E2E-001"},
        headers=_headers("lotus-report", "hold-purge-hold"),
    )
    assert hold.status_code == 201

    refused = assembled_archive.post(
        f"/documents/{document_id}/purge",
        headers=_headers("lotus-report", "hold-purge-refused"),
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "legal_hold_active"

    released = assembled_archive.request(
        "DELETE",
        f"/documents/{document_id}/legal-holds/{hold.json()['legal_hold_id']}",
        json={"release_reason": "Regulatory review complete"},
        headers=_headers("lotus-report", "hold-purge-release"),
    )
    assert released.status_code == 200
    assert released.json()["hold_status"] == "clear"

    purged = assembled_archive.post(
        f"/documents/{document_id}/purge",
        headers=_headers("lotus-report", "hold-purge-complete"),
    )
    denied = assembled_archive.get(
        f"/documents/{document_id}/download",
        headers=_headers("lotus-gateway", "hold-purge-download"),
    )

    assert purged.status_code == 200
    assert purged.json()["purge_status"] == "purged"
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "document_purged"


def test_restart_completes_interrupted_purge_from_durable_state(
    assembled_archive: TestClient,
) -> None:
    document_id = _archive_expired_document(assembled_archive, "restart-purge")
    service = app.state.archive_service
    service.storage = _DeleteThenFailOnceStorage(service.storage.root)

    interrupted = assembled_archive.post(
        f"/documents/{document_id}/purge",
        headers=_headers("lotus-report", "restart-purge-interrupted"),
    )
    assert interrupted.status_code == 500
    assert interrupted.json()["error"]["code"] == "internal_error"

    _clear_runtime_services()
    restarted = TestClient(app, raise_server_exceptions=False)
    try:
        completed = restarted.post(
            f"/documents/{document_id}/purge",
            headers=_headers("lotus-report", "restart-purge-completed"),
        )
        replay = restarted.post(
            f"/documents/{document_id}/purge",
            headers=_headers("lotus-report", "restart-purge-replay"),
        )
    finally:
        restarted.close()

    assert completed.status_code == 200
    assert completed.json()["purge_status"] == "purged"
    assert completed.json()["reason_code"] == "purged"
    assert replay.status_code == 200
    assert replay.json()["reason_code"] == "already_purged"
    assert replay.json()["purged_at"] == completed.json()["purged_at"]


def test_published_bundle_alone_verifies_idea_lifecycle_decision(
    assembled_archive: TestClient,
) -> None:
    created = assembled_archive.post(
        "/documents",
        json=_idea_evidence_pack_payload(),
        headers=_headers("lotus-render", "lifecycle-document"),
    )
    assert created.status_code == 201

    issued = assembled_archive.post(
        f"/documents/{created.json()['document_id']}/idea-lifecycle-decisions",
        json={
            "idea_evidence_pack_id": "irep_e2e_001",
            "idea_candidate_id": "icand_e2e_001",
            "source_correlation_ref": "corr-idea-e2e-001",
        },
        headers={
            **_headers("lotus-idea", "lifecycle-decision"),
            "Idempotency-Key": "idea-lifecycle-e2e-001",
        },
    )
    published = assembled_archive.get("/documents/idea-lifecycle-decisions/verification-keys")

    assert issued.status_code == 201
    assert published.status_code == 200
    decision = IdeaLifecycleDecision.model_validate(issued.json())
    bundle = LifecycleVerificationKeys.model_validate(published.json())
    assert len(bundle.keys) == 1
    assert bundle.keys[0].status == "active"
    assert bundle.keys[0].provenance == "managed"
    assert (
        refuse_lifecycle_decision_against_bundle(
            decision,
            bundle=bundle,
            at_utc=decision.issued_at_utc + timedelta(seconds=1),
        )
        is None
    )


class _DeleteThenFailOnceStorage(FilesystemObjectStorage):
    def __init__(self, root: Path) -> None:
        super().__init__(root, namespace="e2e")
        self._failed = False

    def delete(self, *, key: str) -> None:
        super().delete(key=key)
        if not self._failed:
            self._failed = True
            raise RuntimeError("simulated process loss after object deletion")


def _clear_runtime_services() -> None:
    service = getattr(app.state, "archive_service", None)
    if service is not None:
        service.close()
        del app.state.archive_service
    if hasattr(app.state, "idea_lifecycle_decision_service"):
        del app.state.idea_lifecycle_decision_service


def _headers(caller_service: str, suffix: str) -> dict[str, str]:
    return {
        "X-Correlation-Id": f"corr-e2e-{suffix}",
        "X-Trace-Id": f"trace-e2e-{suffix}",
        "X-Caller-Service": caller_service,
        "X-Actor-Type": "service",
        "X-Actor-Id": f"{caller_service}-e2e",
        "X-Tenant-Id": "tenant-private-bank",
        "X-Region": "SG",
    }


def _document_payload(
    suffix: str,
    *,
    content: bytes = b"archive e2e document",
    expired: bool = False,
) -> dict[str, object]:
    metadata = valid_metadata_input(
        archive_request_id=f"archive-request-{suffix}",
        report_job_id=f"report-job-{suffix}",
        report_request_id=f"report-request-{suffix}",
        snapshot_id=f"snapshot-{suffix}",
        render_job_id=f"render-job-{suffix}",
        render_attempt_id=f"render-attempt-{suffix}",
        retention_start_date="2019-01-01" if expired else "2026-04-25",
        retain_until_date="2020-01-01" if expired else "2033-04-25",
    )
    return {
        "metadata": metadata.model_dump(mode="json"),
        "content_base64": b64encode(content).decode("ascii"),
    }


def _archive_expired_document(client: TestClient, suffix: str) -> str:
    response = client.post(
        "/documents",
        json=_document_payload(suffix, expired=True),
        headers=_headers("lotus-render", f"{suffix}-create"),
    )
    assert response.status_code == 201
    return str(response.json()["document_id"])


def _idea_evidence_pack_payload() -> dict[str, object]:
    metadata = valid_metadata_input(
        archive_request_id="archive-request-idea-e2e",
        report_job_id="report-job-idea-e2e",
        report_request_id="report-request-idea-e2e",
        snapshot_id="snapshot-idea-e2e",
        render_job_id="render-job-idea-e2e",
        render_attempt_id="render-attempt-idea-e2e",
        report_type="proof_pack",
        portfolio_scope="idea_evidence_pack:irep_e2e_001",
        as_of_date="2026-06-24",
        reporting_period_start="2026-06-24",
        reporting_period_end="2026-06-24",
        frequency="event",
        template_id="proof-pack",
        report_data_contract_version="dpm_proof_pack_report_input.v1",
        classification="restricted",
        retention_start_date="2026-06-24",
        retain_until_date="2033-06-24",
        idea_evidence_pack=idea_evidence_pack_summary(
            report_evidence_pack_id="irep_e2e_001",
            candidate_id="icand_e2e_001",
        ),
    )
    return {
        "metadata": metadata.model_dump(mode="json"),
        "content_base64": b64encode(b"idea evidence proof pack e2e").decode("ascii"),
    }
