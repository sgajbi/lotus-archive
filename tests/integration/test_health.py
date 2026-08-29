from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest
from app.main import app
from app.archive.api import archive_service
from app.archive.settings import ArchiveRuntimeSettings


def _service_with_readiness(
    *,
    repository_ready: bool = True,
    storage_ready: bool = True,
    access_audit_ready: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        runtime_readiness=lambda: SimpleNamespace(
            repository_ready=repository_ready,
            storage_ready=storage_ready,
            access_audit_ready=access_audit_ready,
        )
    )


def test_health_endpoints() -> None:
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/health/live").status_code == 200
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "degraded",
        "reason": "explicit_local_development_runtime",
    }


def test_correlation_and_trace_header_propagation() -> None:
    client = TestClient(app)
    response = client.get(
        "/health",
        headers={"X-Correlation-Id": "corr-123", "X-Trace-Id": "trace-456"},
    )
    assert response.status_code == 200
    assert response.headers["X-Correlation-Id"] == "corr-123"
    assert response.headers["X-Trace-Id"] == "trace-456"
    assert "traceparent" not in response.headers


def test_valid_x_trace_id_emits_traceparent() -> None:
    trace_id = "0123456789abcdef0123456789abcdef"
    client = TestClient(app)
    response = client.get(
        "/health",
        headers={"X-Correlation-Id": "corr-123", "X-Trace-Id": trace_id},
    )

    assert response.status_code == 200
    assert response.headers["traceparent"] == f"00-{trace_id}-0000000000000001-01"


def test_traceparent_header_preferred_for_trace_propagation() -> None:
    trace_id = "0123456789abcdef0123456789abcdef"
    client = TestClient(app)
    response = client.get(
        "/health",
        headers={
            "X-Correlation-Id": "corr-456",
            "X-Trace-Id": "trace-ignored",
            "traceparent": f"00-{trace_id}-0000000000000001-01",
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Correlation-Id"] == "corr-456"
    assert response.headers["X-Trace-Id"] == trace_id
    assert response.headers["traceparent"] == f"00-{trace_id}-0000000000000001-01"


def test_missing_trace_header_is_generated() -> None:
    client = TestClient(app)
    response = client.get("/health", headers={"X-Correlation-Id": "corr-generated"})

    assert response.status_code == 200
    assert response.headers["X-Trace-Id"]
    assert response.headers["traceparent"].startswith("00-")


def test_readiness_reports_draining_state() -> None:
    client = TestClient(app)
    app.state.is_draining = True
    try:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "draining"
    finally:
        app.state.is_draining = False


def test_readiness_reports_unavailable_runtime_state() -> None:
    client = TestClient(app)
    app.dependency_overrides[archive_service] = _service_with_readiness
    original_settings = app.state.archive_runtime_settings
    app.state.archive_runtime_settings = ArchiveRuntimeSettings.model_construct(
        runtime_profile="production",
        repository_mode="postgresql",
        storage_mode="filesystem",
        storage_namespace="prod",
        database_url="postgresql://archive/prod",
        max_decoded_document_bytes=1024,
    )
    try:
        response = client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {
            "status": "unavailable",
            "reason": "durable_archive_runtime_missing",
        }
    finally:
        app.state.archive_runtime_settings = original_settings
        app.dependency_overrides.clear()


def test_readiness_reports_measured_repository_outage() -> None:
    app.dependency_overrides[archive_service] = lambda: _service_with_readiness(
        repository_ready=False
    )
    try:
        response = TestClient(app).get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "reason": "archive_repository_unavailable",
    }


def test_readiness_reports_measured_storage_outage() -> None:
    app.dependency_overrides[archive_service] = lambda: _service_with_readiness(storage_ready=False)
    try:
        response = TestClient(app).get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "reason": "archive_storage_unavailable",
    }


def test_readiness_reports_measured_access_audit_outage() -> None:
    app.dependency_overrides[archive_service] = lambda: _service_with_readiness(
        access_audit_ready=False
    )
    try:
        response = TestClient(app).get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "reason": "archive_access_audit_unavailable",
    }


def test_readiness_draining_outranks_measured_outage() -> None:
    app.dependency_overrides[archive_service] = lambda: _service_with_readiness(
        repository_ready=False
    )
    app.state.is_draining = True
    try:
        response = TestClient(app).get("/health/ready")
    finally:
        app.state.is_draining = False
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["status"] == "draining"


def test_metadata_reports_archive_supportability() -> None:
    client = TestClient(app)
    response = client.get("/metadata")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "lotus-archive"
    assert payload["supportability"]["featureKey"] == (
        "archive.observability.archive_supportability"
    )
    assert payload["supportability"]["state"] == "ready"
    assert payload["supportability"]["reason"] == "archive_supportability_ready"
    assert payload["supportability"]["freshnessBucket"] == "current"
    assert payload["supportability"]["retrievalSupported"] is True
    assert payload["supportability"]["retentionSupported"] is True
    assert payload["supportability"]["legalHoldSupported"] is True
    assert payload["supportability"]["accessAuditSupported"] is True
    assert payload["supportability"]["documentLifecycleSupported"] is True
    assert payload["supportability"]["gatewayRetrievalSupported"] is True
    assert payload["supportability"]["workbenchRetrievalSupported"] is True
    assert payload["supportability"]["repositoryReady"] is True
    assert payload["supportability"]["storageReady"] is True
    assert payload["supportability"]["accessAuditReady"] is True
    assert (
        "gateway_backed_document_retrieval" in payload["supportability"]["supportedArchiveFeatures"]
    )
    assert (
        "gateway_backed_workbench_document_retrieval"
        in payload["supportability"]["supportedArchiveFeatures"]
    )
    assert payload["build"]["service"] == "lotus-archive"
    assert payload["build"]["image_digest_posture"] == "not_published"


def test_metadata_reports_measured_repository_unavailability() -> None:
    class UnavailableRepositoryService:
        def runtime_readiness(self) -> SimpleNamespace:
            return SimpleNamespace(
                repository_ready=False,
                storage_ready=True,
                access_audit_ready=True,
            )

    app.dependency_overrides[archive_service] = lambda: UnavailableRepositoryService()
    try:
        response = TestClient(app).get("/metadata")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    supportability = response.json()["supportability"]
    assert supportability["state"] == "unavailable"
    assert supportability["reason"] == "archive_repository_unavailable"
    assert supportability["repositoryReady"] is False
    assert supportability["retrievalSupported"] is False


def test_version_endpoint_reports_runtime_build_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOTUS_ARCHIVE_COMMIT_SHA", "abc123")
    monkeypatch.setenv("LOTUS_ARCHIVE_REPOSITORY_URL", "https://github.com/sgajbi/lotus-archive")
    monkeypatch.setenv("LOTUS_ARCHIVE_BUILD_REF", "refs/heads/main")
    monkeypatch.setenv("LOTUS_ARCHIVE_BUILD_TIMESTAMP_UTC", "2026-07-14T00:00:00Z")
    monkeypatch.setenv("LOTUS_ARCHIVE_CI_RUN_ID", "29290000000")
    monkeypatch.setenv("LOTUS_ARCHIVE_IMAGE_REF", "lotus-archive:abc123")
    monkeypatch.setenv("LOTUS_ARCHIVE_IMAGE_DIGEST", "sha256:" + "b" * 64)

    client = TestClient(app)
    response = client.get("/version")

    assert response.status_code == 200
    assert response.json() == {
        "service": "lotus-archive",
        "version": "0.1.0",
        "commit_sha": "abc123",
        "repository_url": "https://github.com/sgajbi/lotus-archive",
        "git_ref": "refs/heads/main",
        "build_timestamp_utc": "2026-07-14T00:00:00Z",
        "ci_run_id": "29290000000",
        "image_ref": "lotus-archive:abc123",
        "image_digest": "sha256:" + "b" * 64,
        "image_digest_posture": "immutable_digest",
    }


def test_unknown_route_uses_support_safe_error_envelope() -> None:
    client = TestClient(app)
    response = client.get(
        "/unknown-route/not-yet-implemented", headers={"X-Correlation-Id": "corr-404"}
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "The requested resource was not found.",
            "correlation_id": "corr-404",
            "service": "lotus-archive",
        }
    }
