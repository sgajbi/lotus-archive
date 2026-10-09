"""Both strict evidence kinds use existing custody, replay and explicit lineage."""

from base64 import b64encode
from copy import deepcopy
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.archive.api import archive_service
from app.main import app
from tests.fixtures.composite_eligibility import eligibility_payload
from tests.integration.test_archive_documents_api import _headers, _service
from tests.integration.test_composite_custody_api import ClientService
from tests.integration.test_composite_linked_custody import linked_headers


@pytest.fixture
def client(tmp_path: Path) -> Iterator[ClientService]:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            yield api, service
    finally:
        app.dependency_overrides.clear()


def eligibility_custody_journey(client: ClientService, kind: str) -> list[dict[str, Any]]:
    api, _ = client
    offers = [
        eligibility_payload(kind, variant) for variant in ("original", "technical", "corrected")
    ]
    records = []
    for offered in offers:
        response = api.post("/documents", json=offered, headers=linked_headers("lotus-render"))
        assert response.status_code == 201, response.text
        record = response.json()
        assert (
            record["composite_report_identity"] == offered["metadata"]["composite_report_identity"]
        )
        replay = api.post("/documents", json=offered, headers=linked_headers("lotus-render"))
        assert replay.status_code == 201 and replay.json() == record
        records.append(record)
    original, technical, corrected = records
    assert original["composite_report_identity"] == technical["composite_report_identity"]
    assert original["report_revision_id"] == technical["report_revision_id"]
    assert original["checksum"] != technical["checksum"]
    assert original["composite_report_identity"] != corrected["composite_report_identity"]
    for key in ("source_revision_digest", "source_pin", "currency", "revision", "content"):
        changed = deepcopy(offers[0])
        identity = changed["metadata"]["composite_report_identity"]
        if key == "source_revision_digest":
            identity[key] = "9" * 64
        elif key == "source_pin":
            identity["selection"]["months"][0]["proposal_content_hash"] = "sha256:" + "9" * 64
        elif key == "currency":
            identity["selection"]["reporting_currency"] = "EUR"
        elif key == "revision":
            changed["metadata"]["report_revision_id"] = "competing-revision"
        else:
            changed["content_base64"] = offers[2]["content_base64"]
            changed["metadata"]["declared_artifact_sha256"] = corrected["checksum"]
        refused = api.post("/documents", json=changed, headers=linked_headers("lotus-render"))
        assert refused.status_code == 409, refused.text
    assert api.post("/documents", json=offers[0], headers=linked_headers()).status_code == 403
    for source, target in ((original, technical), (technical, corrected)):
        route = f"/documents/{source['document_id']}/correct"
        command = {
            "target_document_id": target["document_id"],
            "transition_reason": "controlled eligibility source lineage",
        }
        assert api.post(route, json=command, headers=_headers()).status_code == 403
        relationship = api.post(route, json=command, headers=linked_headers())
        assert relationship.status_code == 201, relationship.text
        assert api.post(route, json=command, headers=linked_headers()).json() == relationship.json()
    for record, offered in zip(records, offers):
        route = f"/documents/{record['document_id']}"
        held = api.get(route, headers=linked_headers())
        assert held.status_code == 200
        assert (
            held.json()["composite_report_identity"]
            == offered["metadata"]["composite_report_identity"]
        )
        assert (
            api.get(route + "/current", headers=linked_headers()).json()["document_id"]
            == corrected["document_id"]
        )
        downloaded = api.get(route + "/download", headers=linked_headers())
        assert downloaded.status_code == 200
        assert b64encode(downloaded.content).decode("ascii") == offered["content_base64"]
        events = api.get(route + "/source-events", headers=linked_headers())
        assert (
            events.status_code == 200
            and events.json()["events"][0]["composite_report_identity"]
            == record["composite_report_identity"]
        )
        assert api.get(route + "/retention", headers=linked_headers()).status_code == 200
        for suffix in ("", "/download", "/source-events", "/retention", "/current"):
            assert api.get(route + suffix, headers=_headers()).status_code == 403
        audit = api.get(route + "/access-events", headers=linked_headers())
        assert audit.status_code == 200
        assert "binary_download" in [event["event_type"] for event in audit.json()["events"]]
    return records


@pytest.mark.parametrize("kind", ["PUBLISHED", "EVALUATED_ONLY"])
def test_eligibility_original_rerender_correction_and_refusals(
    client: ClientService, kind: str
) -> None:
    eligibility_custody_journey(client, kind)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "foreign"),
        ("composite_id", "foreign"),
        ("reporting_period_start", "2026-01-02"),
        ("reporting_period_end", "2026-02-28"),
        ("as_of_date", "2026-02-01"),
        ("template_version", "v3"),
        ("report_data_contract_version", "composite_review.v3"),
    ],
)
def test_eligibility_enclosing_scope_refuses(client: ClientService, field: str, value: str) -> None:
    api, _ = client
    offered = eligibility_payload()
    offered["metadata"][field] = value
    response = api.post("/documents", json=offered, headers=linked_headers("lotus-render"))
    assert response.status_code == 422, response.text
