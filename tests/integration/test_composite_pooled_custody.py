"""Opaque source/fallback pins retain exact bytes and explicit document lineage."""

from base64 import b64encode
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from app.archive.api import archive_service
from app.main import app
from tests.fixtures.composite_pooled import CASES, pooled_payload
from tests.integration.test_archive_documents_api import _headers, _service
from tests.integration.test_composite_custody_api import ClientService


def pooled_headers(caller: str = "lotus-report") -> dict[str, str]:
    return {**_headers(caller), "X-Tenant-Id": "controlled-tenant", "X-Region": "APAC"}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[ClientService]:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            yield api, service
    finally:
        app.dependency_overrides.clear()


def assert_pooled_reads(api: TestClient, record: dict[str, Any], case: str) -> None:
    offered = pooled_payload(case)
    route = f"/documents/{record['document_id']}"
    assert api.get(route, headers=pooled_headers()).json() == record
    downloaded = api.get(route + "/download", headers=pooled_headers())
    assert downloaded.status_code == 200
    assert b64encode(downloaded.content).decode("ascii") == offered["content_base64"]
    replay = api.post("/documents", json=offered, headers=pooled_headers("lotus-render"))
    assert replay.status_code == 201 and replay.json() == record
    events = api.get(route + "/source-events", headers=pooled_headers())
    assert events.status_code == 200
    assert (
        events.json()["events"][0]["composite_report_identity"]
        == record["composite_report_identity"]
    )
    assert api.get(route + "/retention", headers=pooled_headers()).status_code == 200
    for suffix in ("", "/download", "/source-events", "/retention", "/current"):
        assert api.get(route + suffix, headers=_headers()).status_code == 403
    audit = api.get(route + "/access-events", headers=pooled_headers())
    assert audit.status_code == 200
    assert "binary_download" in [row["event_type"] for row in audit.json()["events"]]


def pooled_custody_journey(client: ClientService) -> list[dict[str, Any]]:
    api, _ = client
    records = []
    for case in CASES:
        offered = pooled_payload(case)
        response = api.post("/documents", json=offered, headers=pooled_headers("lotus-render"))
        assert response.status_code == 201, response.text
        record = response.json()
        assert (
            record["composite_report_identity"] == offered["metadata"]["composite_report_identity"]
        )
        assert_pooled_reads(api, record, case)
        records.append(record)
    original, technical, corrected = records[:3]
    assert original["composite_report_identity"] == technical["composite_report_identity"]
    assert original["report_revision_id"] == technical["report_revision_id"]
    assert original["checksum"] != technical["checksum"]
    selection = corrected["composite_report_identity"]["selection"]
    assert (
        selection["correction_of_calculation_id"]
        == original["composite_report_identity"]["selection"]["calculation_id"]
    )
    for source, target in ((original, technical), (technical, corrected)):
        route = f"/documents/{source['document_id']}/correct"
        command = {
            "target_document_id": target["document_id"],
            "transition_reason": "controlled pooled source lineage",
        }
        assert api.post(route, json=command, headers=_headers()).status_code == 403
        admitted = api.post(route, json=command, headers=pooled_headers())
        assert admitted.status_code == 201, admitted.text
        assert api.post(route, json=command, headers=pooled_headers()).json() == admitted.json()
        assert (
            api.get(f"/documents/{source['document_id']}/current", headers=pooled_headers()).json()[
                "document_id"
            ]
            == target["document_id"]
        )
    for record in records[:3]:
        assert (
            api.get(f"/documents/{record['document_id']}/current", headers=pooled_headers()).json()[
                "document_id"
            ]
            == corrected["document_id"]
        )
    return records


def test_all_source_outcomes_and_retained_correction_journey(client: ClientService) -> None:
    pooled_custody_journey(client)


@pytest.mark.parametrize(
    "change",
    ["source_pin", "source_digest", "currency", "fallback", "predecessor", "revision", "bytes"],
)
def test_immutable_retry_refuses_valid_metadata_or_byte_mutation(
    client: ClientService, change: str
) -> None:
    api, _ = client
    offered = pooled_payload("corrected")
    assert (
        api.post("/documents", json=offered, headers=pooled_headers("lotus-render")).status_code
        == 201
    )
    changed = deepcopy(offered)
    selection = changed["metadata"]["composite_report_identity"]["selection"]
    if change == "source_pin":
        selection["source_pins"][0]["payload_digest"] = "sha256:" + "a" * 64
    elif change == "source_digest":
        selection["response_digest"] = "sha256:" + "b" * 64
    elif change == "currency":
        selection["reporting_currency"] = "EUR"
    elif change == "fallback":
        selection["fallback_policy"] = "ALLOW_MODIFIED_DIETZ"
    elif change == "predecessor":
        selection["predecessor_response_digest"] = "sha256:" + "c" * 64
    elif change == "revision":
        changed["metadata"]["report_revision_id"] = "competing-opaque-revision"
    else:
        other = pooled_payload("original")
        changed["content_base64"] = other["content_base64"]
        changed["metadata"]["declared_artifact_sha256"] = other["metadata"][
            "declared_artifact_sha256"
        ]
    response = api.post("/documents", json=changed, headers=pooled_headers("lotus-render"))
    assert response.status_code == 409, response.text
    assert api.post("/documents", json=offered, headers=pooled_headers()).status_code == 403


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "foreign"),
        ("composite_id", "foreign"),
        ("as_of_date", "2026-01-02"),
        ("reporting_period_start", "2025-01-02"),
        ("reporting_period_end", "2026-01-02"),
        ("template_version", "v4"),
        ("report_data_contract_version", "composite_review.v4"),
    ],
)
def test_enclosing_scope_requires_exact_selector(
    client: ClientService, field: str, value: str
) -> None:
    api, _ = client
    offered = pooled_payload()
    offered["metadata"][field] = value
    response = api.post("/documents", json=offered, headers=pooled_headers("lotus-render"))
    assert response.status_code == 422, response.text
