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
        create_response = client.post("/documents", json=_payload(), headers=_headers())
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
        create_response = client.post("/documents", json=_payload(), headers=_headers())
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
