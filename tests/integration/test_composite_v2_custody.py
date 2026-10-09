from base64 import b64encode
from copy import deepcopy
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.archive.api import archive_service
from app.main import app

from tests.fixtures.composite_v2 import v2_metadata
from tests.fixtures.composite_workbook import workbook_bytes
from tests.integration.test_archive_documents_api import _headers, _service
from tests.integration.test_composite_custody_api import ClientService


@pytest.fixture
def client(tmp_path: Path) -> Iterator[ClientService]:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            yield api, service
    finally:
        app.dependency_overrides.clear()


def v2_payload(*, corrected: bool = False) -> dict[str, Any]:
    content = workbook_bytes("3.02" if corrected else "2.00")
    return {
        "metadata": v2_metadata(content, corrected=corrected),
        "content_base64": b64encode(content).decode("ascii"),
    }


def v2_headers(caller: str = "lotus-report") -> dict[str, str]:
    return {**_headers(caller), "X-Tenant-Id": "tenant-a", "X-Region": "APAC"}


def v2_custody_journey(client: ClientService) -> tuple[dict[str, Any], dict[str, Any]]:
    api, _ = client
    offered = v2_payload()
    response = api.post("/documents", json=offered, headers=v2_headers("lotus-render"))
    assert response.status_code == 201, response.text
    original = response.json()
    document_id = original["document_id"]
    identity = offered["metadata"]["composite_report_identity"]
    assert original["composite_report_identity"] == identity
    assert (
        api.post("/documents", json=offered, headers=v2_headers("lotus-render")).json() == original
    )
    for alteration in ("order", "digest"):
        changed = deepcopy(offered)
        changed_identity = changed["metadata"]["composite_report_identity"]
        if alteration == "order":
            changed_identity["source_products"].reverse()
        else:
            product = changed_identity["source_products"][0]
            product["source_response_digest"] = "sha256:" + "0" * 64
            product["pin"]["selection"]["response_digest"] = product["source_response_digest"]
        refusal = api.post("/documents", json=changed, headers=v2_headers("lotus-render"))
        assert refusal.status_code == 409, refusal.text
    corrected_payload = v2_payload(corrected=True)
    created = api.post("/documents", json=corrected_payload, headers=v2_headers("lotus-render"))
    assert created.status_code == 201, created.text
    corrected = created.json()
    assert (
        corrected["composite_report_identity"]
        == corrected_payload["metadata"]["composite_report_identity"]
    )
    correction = api.post(
        f"/documents/{document_id}/correct",
        json={
            "target_document_id": corrected["document_id"],
            "transition_reason": "source correction",
        },
        headers=v2_headers(),
    )
    assert correction.status_code == 201, correction.text
    current = api.get(f"/documents/{document_id}/current", headers=v2_headers())
    assert current.json()["document_id"] == corrected["document_id"]
    for document, payload in ((original, offered), (corrected, corrected_payload)):
        route = f"/documents/{document['document_id']}"
        assert (
            api.get(route, headers=v2_headers()).json()["composite_report_identity"]
            == payload["metadata"]["composite_report_identity"]
        )
        events = api.get(route + "/source-events", headers=v2_headers()).json()
        assert (
            events["events"][0]["composite_report_identity"]
            == document["composite_report_identity"]
        )
        download = api.get(route + "/download", headers=v2_headers())
        assert download.status_code == 200
        assert b64encode(download.content).decode("ascii") == payload["content_base64"]
        assert api.get(route, headers=_headers()).status_code == 403
        retention = api.get(route + "/retention", headers=v2_headers())
        assert retention.status_code == 200
    retry = api.post("/documents", json=offered, headers=v2_headers("lotus-render"))
    assert retry.status_code == 201
    assert retry.json()["document_id"] == document_id
    assert retry.json()["composite_report_identity"] == identity
    assert retry.json()["superseded_by_document_id"] == corrected["document_id"]
    return original, corrected


def test_v2_original_correction_retry_and_source_events(client: ClientService) -> None:
    v2_custody_journey(client)
