from base64 import b64encode
from hashlib import sha256
from pathlib import Path
from collections.abc import Iterator
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.archive.api import archive_service
from app.archive.service import ArchiveDocumentService
from app.main import app
from tests.fixtures.composite_custody import composite_metadata
from tests.fixtures.composite_workbook import workbook_bytes
from tests.integration.test_archive_documents_api import _headers, _service


ClientService = tuple[TestClient, ArchiveDocumentService]


def payload(content: bytes, revision: str = "original") -> dict[str, Any]:
    return {
        "metadata": composite_metadata(content, revision),
        "content_base64": b64encode(content).decode("ascii"),
    }


@pytest.fixture
def client(tmp_path: Path) -> Iterator[ClientService]:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client, service
    finally:
        app.dependency_overrides.clear()


def composite_custody_journey(
    client: ClientService, tmp_path: Path
) -> None:
    api, service = client
    original = workbook_bytes()
    offered = payload(original)
    created = api.post("/documents", json=offered, headers=_headers("lotus-render"))
    assert created.status_code == 201, created.text
    document = created.json()
    document_id = document["document_id"]
    assert document["portfolio_id"] is None
    assert document["composite_report_identity"] == offered["metadata"]["composite_report_identity"]
    stored = service.repository.get_by_document_id(document_id)
    assert stored is not None
    assert stored.storage_key.endswith(".xlsx")
    assert (tmp_path / "objects" / stored.storage_key).read_bytes() == original
    duplicate = api.post("/documents", json=offered, headers=_headers("lotus-render"))
    assert duplicate.status_code == 201 and duplicate.json()["document_id"] == document_id
    download = api.get(f"/documents/{document_id}/download", headers=_headers())
    assert download.content == original
    assert download.headers["content-type"] == document["mime_type"]
    assert sha256(download.content).hexdigest() == document["checksum"]
    assert ".xlsx" in download.headers["content-disposition"]
    events = api.get(f"/documents/{document_id}/source-events", headers=_headers()).json()
    assert events["composite_id"] == "NEUTRAL_BALANCED"
    assert events["events"][0]["composite_report_identity"] == document["composite_report_identity"]
    assert (
        events["events"][0]["document_evidence_authority"] == "lotus-archive_document_evidence_only"
    )
    assert "storage_key" not in str(events) and "source_response" not in str(events)
    corrected = api.post(
        "/documents",
        json=payload(workbook_bytes("3.02"), "corrected"),
        headers=_headers("lotus-render"),
    ).json()
    correction = api.post(
        f"/documents/{document_id}/correct",
        json={
            "target_document_id": corrected["document_id"],
            "transition_reason": "source correction",
        },
        headers=_headers(),
    )
    assert correction.status_code == 201
    assert api.get(f"/documents/{document_id}/download", headers=_headers()).content == original
    current = api.get(f"/documents/{document_id}/current", headers=_headers()).json()
    assert current["document_id"] == corrected["document_id"]
    retention = api.get(f"/documents/{document_id}/retention", headers=_headers()).json()
    assert retention["retention_policy_id"] == "generated-report-standard"
    hold = api.post(
        f"/documents/{document_id}/legal-holds",
        headers=_headers(),
        json={"hold_reason": "retained correction evidence", "authority_reference": "case-176"},
    )
    assert hold.status_code == 201
    assert (
        api.get(f"/documents/{document_id}/retention", headers=_headers()).json()[
            "legal_hold_count"
        ]
        == 1
    )
    audit = api.get(f"/documents/{document_id}/access-events", headers=_headers()).json()
    assert "binary_download" in [event["event_type"] for event in audit["events"]]


@pytest.mark.parametrize(
    "field,value",
    [
        ("portfolio_id", "fake-core"),
        ("portfolio_scope", "single_portfolio"),
        ("composite_id", "other-composite"),
        ("composite_report_identity", None),
        ("report_revision_id", None),
        ("document_reference", None),
        ("declared_artifact_sha256", None),
        ("template_id", "portfolio-review"),
        ("mime_type", "application/pdf"),
        ("output_format", "pdf"),
        ("report_type", "arbitrary"),
        ("as_of_date", "2026-02-01"),
    ],
)
def test_invalid_composite_contract_refused_before_storage(
    client: ClientService, field: str, value: object
) -> None:
    api, service = client
    offered = payload(workbook_bytes())
    offered["metadata"][field] = value
    response = api.post("/documents", json=offered, headers=_headers("lotus-render"))
    assert response.status_code == 422
    assert service.repository.get_by_archive_request_id("archive-composite-original") is None


def test_corrupt_bytes_hash_conflicts_and_tenant_refusal(client: ClientService) -> None:
    api, service = client
    original = payload(workbook_bytes())
    document = api.post("/documents", json=original, headers=_headers("lotus-render")).json()
    different = payload(workbook_bytes("2.00"))
    assert (
        api.post("/documents", json=different, headers=_headers("lotus-render")).status_code == 409
    )
    corrupt = payload(b"%PDF-1.4")
    assert api.post("/documents", json=corrupt, headers=_headers("lotus-render")).status_code == 400
    wrong_hash = payload(workbook_bytes())
    wrong_hash["metadata"]["declared_artifact_sha256"] = "0" * 64
    assert (
        api.post("/documents", json=wrong_hash, headers=_headers("lotus-render")).status_code == 422
    )
    other = {**_headers(), "X-Tenant-Id": "tenant-other"}
    for suffix in ("", "/download", "/source-events", "/retention"):
        assert (
            api.get(f"/documents/{document['document_id']}{suffix}", headers=other).status_code
            == 403
        )
    assert (
        api.post(
            "/documents", json=original, headers={**other, "X-Caller-Service": "lotus-render"}
        ).status_code
        == 403
    )
    retained = service.repository.get_by_archive_request_id("archive-composite-original")
    assert retained is not None and retained.document_id == document["document_id"]
