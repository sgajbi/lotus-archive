from fastapi.testclient import TestClient
from app.main import app


def test_e2e_smoke() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_metadata_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/metadata")
    assert response.status_code == 200
    assert response.json()["service"].startswith("lotus-")
    assert response.json()["archivePosture"]["supportedArchiveFeatures"] == [
        "generated_document_archival",
        "controlled_document_metadata_lookup",
        "controlled_document_binary_download",
        "access_audit_for_archive_api",
        "retention_policy_posture",
        "purge_eligibility_and_execution",
        "legal_hold_set_release_with_purge_blocking",
        "document_lifecycle_relationships",
        "current_document_resolution",
        "report_to_archive_handoff",
        "gateway_backed_document_retrieval",
    ]
