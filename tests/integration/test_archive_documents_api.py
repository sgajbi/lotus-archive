from base64 import b64encode
from pathlib import Path

from fastapi.testclient import TestClient

from app.archive.api import archive_service
from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import InMemoryAccessAuditRepository
from app.archive.repository import InMemoryArchiveDocumentRepository
from app.archive.service import ArchiveDocumentService
from app.archive.storage import FilesystemObjectStorage
from app.main import app
from tests.unit.test_archive_writer import valid_metadata_input


def _service(tmp_path: Path) -> ArchiveDocumentService:
    repository = InMemoryArchiveDocumentRepository()
    storage = FilesystemObjectStorage(tmp_path / "objects")
    return ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=InMemoryAccessAuditRepository(),
    )


def _headers(caller_service: str = "lotus-report") -> dict[str, str]:
    return {
        "X-Correlation-Id": "corr-api",
        "X-Trace-Id": "trace-api",
        "X-Caller-Service": caller_service,
        "X-Actor-Type": "service",
        "X-Actor-Id": "report-worker",
    }


def _payload(content: bytes = b"portfolio review pdf bytes") -> dict[str, object]:
    return {
        "metadata": valid_metadata_input().model_dump(mode="json"),
        "content_base64": b64encode(content).decode("ascii"),
    }


def _payload_with_id(archive_request_id: str, content: bytes) -> dict[str, object]:
    payload = _payload(content)
    payload["metadata"] = valid_metadata_input(
        archive_request_id=archive_request_id,
        report_job_id=f"report-job-{archive_request_id}",
        render_job_id=f"render-job-{archive_request_id}",
        render_attempt_id=f"render-attempt-{archive_request_id}",
    ).model_dump(mode="json")
    return payload


def _purge_eligible_payload() -> dict[str, object]:
    payload = _payload()
    metadata = valid_metadata_input(
        retention_start_date="2019-01-01",
        retain_until_date="2020-01-01",
    ).model_dump(mode="json")
    payload["metadata"] = metadata
    return payload


def _proof_pack_payload() -> dict[str, object]:
    payload = _payload(content=b"proof pack pdf bytes")
    payload["metadata"] = valid_metadata_input(
        archive_request_id="archive-request-proof-pack-001",
        report_job_id="report-job-proof-pack-001",
        report_request_id="report-request-proof-pack-001",
        snapshot_id="snapshot-proof-pack-001",
        render_job_id="render-job-proof-pack-001",
        render_attempt_id="render-attempt-proof-pack-001",
        report_type="proof_pack",
        portfolio_scope="proof_pack:dpp_001",
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        as_of_date="2026-05-03",
        reporting_period_start="2026-05-03",
        reporting_period_end="2026-05-03",
        frequency="event",
        template_id="proof-pack",
        report_data_contract_version="dpm_proof_pack_report_input.v1",
        classification="restricted",
        retention_start_date="2019-01-01",
        retain_until_date="2020-01-01",
    ).model_dump(mode="json")
    return payload


def test_document_create_lookup_download_and_access_events_api(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        create_response = client.post("/documents", json=_payload(), headers=_headers())
        assert create_response.status_code == 201
        body = create_response.json()
        document_id = body["document_id"]
        assert body["archive_request_id"] == "archive-request-001"
        assert "storage_key" not in body

        metadata_response = client.get(
            f"/documents/{document_id}",
            headers=_headers(caller_service="lotus-gateway"),
        )
        assert metadata_response.status_code == 200
        assert metadata_response.json()["document_id"] == document_id
        assert "storage_key" not in metadata_response.json()

        download_response = client.get(
            f"/documents/{document_id}/download",
            headers=_headers(caller_service="lotus-gateway"),
        )
        assert download_response.status_code == 200
        assert download_response.content == b"portfolio review pdf bytes"
        assert download_response.headers["content-type"] == "application/pdf"
        assert download_response.headers["x-document-checksum-algorithm"] == "sha256"

        events_response = client.get(
            f"/documents/{document_id}/access-events",
            headers=_headers(),
        )
        assert events_response.status_code == 200
        assert [event["event_type"] for event in events_response.json()["events"]] == [
            "archive_create",
            "metadata_read",
            "binary_download",
            "access_events_read",
        ]
    finally:
        app.dependency_overrides.clear()


def test_proof_pack_report_archive_lifecycle_preserves_retention_and_audit(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        create_response = client.post("/documents", json=_proof_pack_payload(), headers=_headers())
        assert create_response.status_code == 201
        document_id = create_response.json()["document_id"]
        assert create_response.json()["report_type"] == "proof_pack"
        assert create_response.json()["template_id"] == "proof-pack"

        download_response = client.get(
            f"/documents/{document_id}/download",
            headers=_headers(caller_service="lotus-gateway"),
        )
        assert download_response.status_code == 200
        assert download_response.content == b"proof pack pdf bytes"

        hold_response = client.post(
            f"/documents/{document_id}/legal-holds",
            json={
                "hold_reason": "Pre-trade proof-pack compliance review",
                "authority_reference": "DPM-PROOF-PACK-CASE-001",
            },
            headers=_headers(),
        )
        assert hold_response.status_code == 201
        legal_hold_id = hold_response.json()["legal_hold_id"]

        blocked_purge = client.post(f"/documents/{document_id}/purge", headers=_headers())
        assert blocked_purge.status_code == 409
        assert blocked_purge.json()["error"]["code"] == "legal_hold_active"

        release_response = client.request(
            "DELETE",
            f"/documents/{document_id}/legal-holds/{legal_hold_id}",
            json={"release_reason": "Compliance review complete"},
            headers=_headers(),
        )
        assert release_response.status_code == 200

        purge_response = client.post(f"/documents/{document_id}/purge", headers=_headers())
        assert purge_response.status_code == 200
        assert purge_response.json()["purged"] is True

        events_response = client.get(
            f"/documents/{document_id}/access-events",
            headers=_headers(),
        )
        assert events_response.status_code == 200
        event_types = [event["event_type"] for event in events_response.json()["events"]]
        assert event_types == [
            "archive_create",
            "binary_download",
            "legal_hold_set",
            "legal_hold_release",
            "purge_execution",
            "access_events_read",
        ]
    finally:
        app.dependency_overrides.clear()


def test_archive_metrics_expose_bounded_operation_status_and_size_labels(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        create_response = client.post("/documents", json=_payload(), headers=_headers())
        assert create_response.status_code == 201
        body = create_response.json()
        document_id = body["document_id"]

        metadata_response = client.get(
            f"/documents/{document_id}",
            headers=_headers(caller_service="lotus-gateway"),
        )
        assert metadata_response.status_code == 200

        download_response = client.get(
            f"/documents/{document_id}/download",
            headers=_headers(caller_service="lotus-gateway"),
        )
        assert download_response.status_code == 200

        retention_response = client.get(
            f"/documents/{document_id}/retention",
            headers=_headers(),
        )
        assert retention_response.status_code == 200

        metrics_response = client.get("/metrics")
        assert metrics_response.status_code == 200
        metrics_text = metrics_response.text

        expected_metrics = [
            'lotus_archive_operations_total{failure_category="none",operation="archive_create",status="archived"}',
            'lotus_archive_operations_total{failure_category="none",operation="metadata_lookup",status="archived"}',
            'lotus_archive_operations_total{failure_category="none",operation="binary_download",status="succeeded"}',
            'lotus_archive_operations_total{failure_category="none",operation="retention_lookup",status="clear"}',
        ]
        for expected_metric in expected_metrics:
            assert expected_metric in metrics_text
        assert "lotus_archive_operation_duration_seconds_count" in metrics_text
        assert "lotus_archive_document_size_bytes_count" in metrics_text
        assert document_id not in metrics_text
        assert body["report_job_id"] not in metrics_text
        assert body["render_job_id"] not in metrics_text
        assert "corr-api" not in metrics_text
        assert "trace-api" not in metrics_text
        assert "PB_SG_GLOBAL_BAL_001" not in metrics_text
        assert "client-ref-001" not in metrics_text
        assert "storage_key" not in metrics_text
    finally:
        app.dependency_overrides.clear()


def test_document_api_requires_caller_context(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.post("/documents", json=_payload(), headers={"X-Correlation-Id": "corr"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "caller_context_missing"


def test_document_api_denies_direct_workbench_archive_create(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.post(
            "/documents",
            json=_payload(),
            headers=_headers(caller_service="lotus-workbench"),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "authorization_failed"


def test_document_download_reports_checksum_mismatch(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        create_response = client.post(
            "/documents", json=_purge_eligible_payload(), headers=_headers()
        )
        document_id = create_response.json()["document_id"]
        metadata = service.repository.get_by_document_id(document_id)
        assert metadata is not None
        (tmp_path / "objects" / metadata.storage_key).write_bytes(b"corrupt")

        response = client.get(
            f"/documents/{document_id}/download",
            headers=_headers(caller_service="lotus-gateway"),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "document_checksum_mismatch"


def test_document_download_reports_missing_binary(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        create_response = client.post(
            "/documents", json=_purge_eligible_payload(), headers=_headers()
        )
        document_id = create_response.json()["document_id"]
        metadata = service.repository.get_by_document_id(document_id)
        assert metadata is not None
        (tmp_path / "objects" / metadata.storage_key).unlink()

        response = client.get(
            f"/documents/{document_id}/download",
            headers=_headers(caller_service="lotus-gateway"),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "document_binary_missing"


def test_document_metadata_lookup_reports_not_found(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        response = client.get(
            "/documents/doc_missing",
            headers=_headers(caller_service="lotus-gateway"),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "document_not_found"


def test_document_create_reports_metadata_validation_failure(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    payload = _payload()
    payload["content_base64"] = "not-valid-base64"
    try:
        response = client.post("/documents", json=payload, headers=_headers())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "metadata_validation_failed"


def test_document_create_reports_duplicate_request_conflict(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        first = client.post("/documents", json=_payload(), headers=_headers())
        assert first.status_code == 201

        second = client.post("/documents", json=_payload(b"changed"), headers=_headers())
    finally:
        app.dependency_overrides.clear()

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "duplicate_archive_request"


def test_retention_legal_hold_and_purge_api_flow(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        create_response = client.post(
            "/documents", json=_purge_eligible_payload(), headers=_headers()
        )
        document_id = create_response.json()["document_id"]

        retention_response = client.get(
            f"/documents/{document_id}/retention",
            headers=_headers(),
        )
        assert retention_response.status_code == 200
        assert retention_response.json()["legal_hold_count"] == 0

        hold_response = client.post(
            f"/documents/{document_id}/legal-holds",
            json={
                "hold_reason": "Regulatory review",
                "authority_reference": "CASE-001",
            },
            headers=_headers(),
        )
        assert hold_response.status_code == 201
        legal_hold_id = hold_response.json()["legal_hold_id"]

        blocked_purge = client.post(f"/documents/{document_id}/purge", headers=_headers())
        assert blocked_purge.status_code == 409
        assert blocked_purge.json()["error"]["code"] == "legal_hold_active"

        release_response = client.request(
            "DELETE",
            f"/documents/{document_id}/legal-holds/{legal_hold_id}",
            json={"release_reason": "Review complete"},
            headers=_headers(),
        )
        assert release_response.status_code == 200
        assert release_response.json()["hold_status"] == "clear"

        purge_response = client.post(f"/documents/{document_id}/purge", headers=_headers())
        assert purge_response.status_code == 200
        assert purge_response.json()["purged"] is True
        assert purge_response.json()["purge_status"] == "purged"

        events_response = client.get(
            f"/documents/{document_id}/access-events",
            headers=_headers(),
        )
        assert events_response.status_code == 200
        event_types = [event["event_type"] for event in events_response.json()["events"]]
        assert "legal_hold_set" in event_types
        assert "legal_hold_release" in event_types
        assert "purge_execution" in event_types
    finally:
        app.dependency_overrides.clear()


def test_purge_evaluation_reports_retention_elapsed_for_eligible_document(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        create_response = client.post(
            "/documents", json=_purge_eligible_payload(), headers=_headers()
        )
        document_id = create_response.json()["document_id"]

        response = client.post(
            f"/documents/{document_id}/purge-evaluation",
            headers=_headers(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["purge_eligible"] is True
    assert response.json()["reason_code"] == "retention_elapsed"


def test_legal_hold_release_reports_not_found(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        create_response = client.post("/documents", json=_payload(), headers=_headers())
        document_id = create_response.json()["document_id"]
        response = client.request(
            "DELETE",
            f"/documents/{document_id}/legal-holds/hold_missing",
            json={"release_reason": "No longer needed"},
            headers=_headers(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "legal_hold_not_found"


def test_document_lifecycle_api_preserves_history_and_resolves_current(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        historical_response = client.post(
            "/documents",
            json=_payload_with_id("archive-request-history", b"historical"),
            headers=_headers(),
        )
        current_response = client.post(
            "/documents",
            json=_payload_with_id("archive-request-current", b"current"),
            headers=_headers(),
        )
        historical_id = historical_response.json()["document_id"]
        current_id = current_response.json()["document_id"]

        lifecycle_response = client.post(
            f"/documents/{historical_id}/supersede",
            json={
                "target_document_id": current_id,
                "transition_reason": "Approved report replaced draft archive record",
            },
            headers=_headers(),
        )
        historical_lookup = client.get(
            f"/documents/{historical_id}",
            headers=_headers(caller_service="lotus-gateway"),
        )
        current_lookup = client.get(
            f"/documents/{historical_id}/current",
            headers=_headers(caller_service="lotus-gateway"),
        )
        events_response = client.get(
            f"/documents/{historical_id}/access-events",
            headers=_headers(),
        )
    finally:
        app.dependency_overrides.clear()

    assert lifecycle_response.status_code == 201
    assert lifecycle_response.json()["transition_type"] == "supersede"
    assert lifecycle_response.json()["current_document_id"] == current_id
    assert historical_lookup.status_code == 200
    assert historical_lookup.json()["document_id"] == historical_id
    assert historical_lookup.json()["superseded_by_document_id"] == current_id
    assert current_lookup.status_code == 200
    assert current_lookup.json()["document_id"] == current_id
    assert current_lookup.json()["supersedes_document_id"] == historical_id
    event_types = [event["event_type"] for event in events_response.json()["events"]]
    assert "lifecycle_supersede" in event_types
    assert "current_document_read" in event_types


def test_document_lifecycle_api_rejects_conflicting_transition(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        first = client.post(
            "/documents",
            json=_payload_with_id("archive-request-first", b"first"),
            headers=_headers(),
        ).json()["document_id"]
        second = client.post(
            "/documents",
            json=_payload_with_id("archive-request-second", b"second"),
            headers=_headers(),
        ).json()["document_id"]
        third = client.post(
            "/documents",
            json=_payload_with_id("archive-request-third", b"third"),
            headers=_headers(),
        ).json()["document_id"]
        assert (
            client.post(
                f"/documents/{first}/correct",
                json={
                    "target_document_id": second,
                    "transition_reason": "Corrected report package",
                },
                headers=_headers(),
            ).status_code
            == 201
        )

        response = client.post(
            f"/documents/{first}/reissue",
            json={
                "target_document_id": third,
                "transition_reason": "Invalid second transition",
            },
            headers=_headers(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "supersession_conflict"


def test_document_lifecycle_api_reissue_and_unsupported_transition_errors(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        source = client.post(
            "/documents",
            json=_payload_with_id("archive-request-reissue-api-source", b"source"),
            headers=_headers(),
        ).json()["document_id"]
        target = client.post(
            "/documents",
            json=_payload_with_id("archive-request-reissue-api-target", b"target"),
            headers=_headers(),
        ).json()["document_id"]

        reissue_response = client.post(
            f"/documents/{source}/reissue",
            json={
                "target_document_id": target,
                "transition_reason": "Client delivery reissue",
            },
            headers=_headers(),
        )
        unsupported_response = client.post(
            f"/documents/{target}/reissue",
            json={
                "target_document_id": target,
                "transition_reason": "Invalid self transition",
            },
            headers=_headers(),
        )
    finally:
        app.dependency_overrides.clear()

    assert reissue_response.status_code == 201
    assert reissue_response.json()["transition_type"] == "reissue"
    assert unsupported_response.status_code == 409
    assert unsupported_response.json()["error"]["code"] == "unsupported_lifecycle_transition"


def test_purge_api_reports_not_eligible_before_retention_elapsed(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    try:
        create_response = client.post("/documents", json=_payload(), headers=_headers())
        document_id = create_response.json()["document_id"]
        response = client.post(f"/documents/{document_id}/purge", headers=_headers())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "purge_not_eligible"
