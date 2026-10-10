"""Historical selectors retain immutable exact bytes under existing custody controls."""

from base64 import b64decode
from copy import deepcopy

import pytest

from tests.fixtures.composite_historical import IDENTITIES, historical_payload
from tests.integration.test_composite_amendment_custody import amendment_headers, client
from tests.integration.test_composite_custody_api import ClientService

__all__ = ["client"]


@pytest.mark.parametrize("case", IDENTITIES)
def test_historical_custody_exact_replay_download_current_and_tenant(
    client: ClientService, case: str
) -> None:
    api, _ = client
    original = historical_payload(case)
    technical = historical_payload(case, "technical")
    records = []
    for offer in (original, technical):
        response = api.post("/documents", json=offer, headers=amendment_headers("lotus-render"))
        assert response.status_code == 201, response.text
        record = response.json()
        assert (
            api.post("/documents", json=offer, headers=amendment_headers("lotus-render")).json()
            == record
        )
        route = f"/documents/{record['document_id']}"
        assert (
            api.get(route, headers=amendment_headers()).json()["composite_report_identity"]
            == offer["metadata"]["composite_report_identity"]
        )
        assert api.get(route + "/download", headers=amendment_headers()).content == b64decode(
            offer["content_base64"]
        )
        assert api.get(route + "/retention", headers=amendment_headers()).status_code == 200
        assert (
            api.get(route, headers={**amendment_headers(), "x-tenant-id": "foreign"}).status_code
            == 403
        )
        records.append(record)
    assert records[0]["composite_report_identity"] == records[1]["composite_report_identity"]
    route = f"/documents/{records[0]['document_id']}"
    response = api.post(
        route + "/correct",
        json={
            "target_document_id": records[1]["document_id"],
            "transition_reason": "controlled technical rerender",
        },
        headers=amendment_headers(),
    )
    assert response.status_code == 201, response.text
    assert (
        api.get(route + "/current", headers=amendment_headers()).json()["document_id"]
        == records[1]["document_id"]
    )
    changed = deepcopy(original)
    changed["metadata"]["composite_report_identity"]["source_revision_digest"] = "0" * 64
    assert (
        api.post("/documents", json=changed, headers=amendment_headers("lotus-render")).status_code
        == 409
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "foreign"),
        ("composite_id", "foreign"),
        ("template_version", "v6"),
        ("as_of_date", "2026-09-29"),
        ("report_data_contract_version", "composite_review.v6"),
    ],
)
def test_historical_enclosing_scope_refuses(client: ClientService, field: str, value: str) -> None:
    api, _ = client
    offer = historical_payload("v2-correction-3-published")
    offer["metadata"][field] = value
    response = api.post("/documents", json=offer, headers=amendment_headers("lotus-render"))
    assert response.status_code == 422, response.text
