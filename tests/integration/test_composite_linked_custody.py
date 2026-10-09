"""Existing custody path preserves strict linked identity and immutable bytes."""

from base64 import b64encode
from copy import deepcopy
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.archive.api import archive_service
from app.main import app
from tests.fixtures.composite_linked import linked_payload
from tests.integration.test_archive_documents_api import _headers, _service
from tests.integration.test_composite_custody_api import ClientService


def linked_headers(caller: str = "lotus-report") -> dict[str, str]:
    return {**_headers(caller), "X-Tenant-Id": "synthetic-tenant-a", "X-Region": "APAC"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[ClientService]:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            yield api, service
    finally:
        app.dependency_overrides.clear()


def linked_custody_journey(client: ClientService) -> tuple[dict[str, Any], dict[str, Any]]:
    api, _ = client
    offered = linked_payload()
    response = api.post("/documents", json=offered, headers=linked_headers("lotus-render"))
    assert response.status_code == 201, response.text
    original = response.json()
    document_id = original["document_id"]
    assert original["composite_report_identity"] == offered["metadata"]["composite_report_identity"]
    assert (
        api.post("/documents", json=offered, headers=linked_headers("lotus-render")).json()
        == original
    )
    for change in ("digest", "currency", "content", "null_presence"):
        changed = deepcopy(offered)
        if change == "digest":
            changed["metadata"]["composite_report_identity"]["source_revision_digest"] = "9" * 64
        elif change == "currency":
            changed["metadata"]["composite_report_identity"]["selection"]["source_request"][
                "reporting_currency"
            ] = "EUR"
        elif change == "null_presence":
            del changed["metadata"]["composite_report_identity"]["selection"]["source_request"][
                "restatement_sequence"
            ]
        else:
            replacement = linked_payload(corrected=True)
            changed["content_base64"] = replacement["content_base64"]
            changed["metadata"]["declared_artifact_sha256"] = replacement["metadata"][
                "declared_artifact_sha256"
            ]
        refused = api.post("/documents", json=changed, headers=linked_headers("lotus-render"))
        assert refused.status_code == 409, refused.text
    corrected_payload = linked_payload(corrected=True)
    response = api.post(
        "/documents", json=corrected_payload, headers=linked_headers("lotus-render")
    )
    assert response.status_code == 201, response.text
    corrected = response.json()
    correction_body = {
        "target_document_id": corrected["document_id"],
        "transition_reason": "controlled linked-source correction",
    }
    route = f"/documents/{document_id}"
    assert api.post(route + "/correct", json=correction_body, headers=_headers()).status_code == 403
    correction = api.post(route + "/correct", json=correction_body, headers=linked_headers())
    assert correction.status_code == 201, correction.text
    assert (
        api.post(route + "/correct", json=correction_body, headers=linked_headers()).json()
        == correction.json()
    )
    assert (
        api.get(route + "/current", headers=linked_headers()).json()["document_id"]
        == corrected["document_id"]
    )
    for document, source in ((original, offered), (corrected, corrected_payload)):
        route = f"/documents/{document['document_id']}"
        record = api.get(route, headers=linked_headers()).json()
        assert (
            record["composite_report_identity"] == source["metadata"]["composite_report_identity"]
        )
        events = api.get(route + "/source-events", headers=linked_headers()).json()
        assert (
            events["events"][0]["composite_report_identity"] == record["composite_report_identity"]
        )
        download = api.get(route + "/download", headers=linked_headers())
        assert download.status_code == 200
        assert b64encode(download.content).decode("ascii") == source["content_base64"]
        assert api.get(route + "/retention", headers=linked_headers()).status_code == 200
        for suffix in ("", "/download", "/source-events", "/retention"):
            assert api.get(route + suffix, headers=_headers()).status_code == 403
        audit = api.get(route + "/access-events", headers=linked_headers()).json()
        assert "binary_download" in [event["event_type"] for event in audit["events"]]
    retry = api.post("/documents", json=offered, headers=linked_headers("lotus-render"))
    assert retry.status_code == 201 and retry.json()["document_id"] == document_id
    assert retry.json()["composite_report_identity"] == original["composite_report_identity"]
    return original, corrected


def test_linked_original_correction_conflicts_and_source_events(client: ClientService) -> None:
    linked_custody_journey(client)


@pytest.mark.parametrize(
    "field,value",
    [
        ("template_version", "v1"),
        ("template_version", "v2"),
        ("report_data_contract_version", "composite_review.v1"),
        ("report_data_contract_version", "composite_review.v2"),
        ("tenant_id", "foreign"),
        ("composite_id", "foreign"),
        ("reporting_period_start", "2026-01-02"),
        ("reporting_period_end", "2026-02-27"),
        ("as_of_date", "2026-03-01"),
    ],
)
def test_linked_enclosing_scope_and_axes_refuse(
    client: ClientService, field: str, value: str
) -> None:
    api, _ = client
    offered = linked_payload()
    offered["metadata"][field] = value
    refused = api.post("/documents", json=offered, headers=linked_headers("lotus-render"))
    assert refused.status_code == 422, refused.text
