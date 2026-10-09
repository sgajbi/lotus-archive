"""Synthetic XLSX component custody; no actual Report/Manage amendment delivery."""

from base64 import b64encode
from copy import deepcopy
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.archive.api import archive_service
from app.main import app
from tests.fixtures.composite_amendment import SELECTIONS, amendment_payload
from tests.integration.test_archive_documents_api import _headers, _service
from tests.integration.test_composite_custody_api import ClientService


def amendment_headers(caller: str = "lotus-report") -> dict[str, str]:
    return {**_headers(caller), "x-tenant-id": "synthetic-tenant", "x-region": "APAC"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[ClientService]:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            yield api, service
    finally:
        app.dependency_overrides.clear()


def amendment_custody_journey(client: ClientService, case: str) -> list[dict[str, Any]]:
    api, _ = client
    offers = [
        amendment_payload(case, variant) for variant in ("original", "technical", "corrected")
    ]
    records = []
    for offer in offers:
        response = api.post("/documents", json=offer, headers=amendment_headers("lotus-render"))
        assert response.status_code == 201, response.text
        record = response.json()
        assert record["composite_report_identity"] == offer["metadata"]["composite_report_identity"]
        replay = api.post("/documents", json=offer, headers=amendment_headers("lotus-render"))
        assert replay.status_code == 201 and replay.json() == record
        records.append(record)
    original, technical, corrected = records
    assert original["composite_report_identity"] == technical["composite_report_identity"]
    assert original["checksum"] != technical["checksum"]
    assert original["composite_report_identity"] != corrected["composite_report_identity"]
    for source, target in ((original, technical), (technical, corrected)):
        route = f"/documents/{source['document_id']}/correct"
        command = {
            "target_document_id": target["document_id"],
            "transition_reason": "synthetic custody relationship only",
        }
        assert api.post(route, json=command, headers=_headers()).status_code == 403
        relationship = api.post(route, json=command, headers=amendment_headers())
        assert relationship.status_code == 201, relationship.text
        assert (
            api.post(route, json=command, headers=amendment_headers()).json() == relationship.json()
        )
    for record, offer in zip(records, offers, strict=True):
        route = f"/documents/{record['document_id']}"
        held = api.get(route, headers=amendment_headers())
        assert held.status_code == 200
        assert (
            held.json()["composite_report_identity"]
            == offer["metadata"]["composite_report_identity"]
        )
        download = api.get(route + "/download", headers=amendment_headers())
        assert (
            download.status_code == 200
            and b64encode(download.content).decode() == offer["content_base64"]
        )
        assert (
            api.get(route + "/current", headers=amendment_headers()).json()["document_id"]
            == corrected["document_id"]
        )
        events = api.get(route + "/source-events", headers=amendment_headers())
        assert events.status_code == 200
        assert (
            events.json()["events"][0]["composite_report_identity"]
            == record["composite_report_identity"]
        )
        assert api.get(route + "/retention", headers=amendment_headers()).status_code == 200
        for suffix in ("", "/download", "/source-events", "/retention", "/current"):
            assert api.get(route + suffix, headers=_headers()).status_code == 403
        audit = api.get(route + "/access-events", headers=amendment_headers())
        assert audit.status_code == 200
        assert "binary_download" in [event["event_type"] for event in audit.json()["events"]]
    return records


@pytest.mark.parametrize("case", SELECTIONS)
def test_amendment_custody_retains_complete_ordered_lineage(
    client: ClientService, case: str
) -> None:
    amendment_custody_journey(client, case)


@pytest.mark.parametrize("change", ["receipt", "order", "definition", "parent"])
def test_existing_request_refuses_changed_valid_lineage(client: ClientService, change: str) -> None:
    api, _ = client
    offer = amendment_payload()
    assert (
        api.post("/documents", json=offer, headers=amendment_headers("lotus-render")).status_code
        == 201
    )
    changed = deepcopy(offer)
    selection = changed["metadata"]["composite_report_identity"]["selection"]
    month = selection["months"][0]
    if change == "receipt":
        month["lineage_receipts"][0]["receipt_content_hash"] = "sha256:" + "0" * 64
    elif change == "order":
        month["lineage_receipts"].reverse()
    elif change == "definition":
        selection["definition_version"] += "-other"
    else:
        month["parent_publication_response_digest"] = "sha256:" + "0" * 64
    response = api.post("/documents", json=changed, headers=amendment_headers("lotus-render"))
    assert response.status_code == 409, response.text
    assert api.post("/documents", json=offer, headers=amendment_headers()).status_code == 403


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "foreign"),
        ("composite_id", "foreign"),
        ("template_version", "v4"),
        ("report_data_contract_version", "composite_review.v5"),
        ("reporting_period_end", "2026-10-31"),
        ("as_of_date", "2026-09-29"),
    ],
)
def test_amendment_enclosing_scope_refuses(client: ClientService, field: str, value: str) -> None:
    api, _ = client
    offer = amendment_payload()
    offer["metadata"][field] = value
    response = api.post("/documents", json=offer, headers=amendment_headers("lotus-render"))
    assert response.status_code == 422, response.text
