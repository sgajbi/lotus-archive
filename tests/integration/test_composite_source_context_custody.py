"""Registered Archive custody of actual v8 handoffs; not joined runtime proof."""

from base64 import b64decode
from copy import deepcopy
from typing import Any

import pytest

from tests.fixtures.composite_source_context import CASES, context_payload
from tests.integration.test_archive_documents_api import _headers
from tests.integration.test_composite_amendment_custody import client
from tests.integration.test_composite_custody_api import ClientService

__all__ = ["client"]
pytestmark = pytest.mark.filterwarnings("error:Pydantic serializer warnings:UserWarning")


def context_headers(offer: dict[str, Any], caller: str = "lotus-report") -> dict[str, str]:
    return {
        **_headers(caller),
        "X-Tenant-Id": offer["metadata"]["tenant_id"],
        "X-Region": offer["metadata"]["region"],
    }


def context_custody_journey(client: ClientService) -> list[dict[str, Any]]:
    api, _ = client
    records = []
    offers = [context_payload(case) for case in ("original", "corrected")]
    for offer in offers:
        response = api.post(
            "/documents", json=offer, headers=context_headers(offer, "lotus-render")
        )
        assert response.status_code == 201, response.text
        record = response.json()
        assert record["composite_report_identity"] == offer["metadata"]["composite_report_identity"]
        assert record["report_revision_id"] == offer["metadata"]["report_revision_id"]
        assert (
            api.post(
                "/documents", json=offer, headers=context_headers(offer, "lotus-render")
            ).json()
            == record
        )
        records.append(record)
    original, corrected = records
    assert original["report_revision_id"] != corrected["report_revision_id"]
    assert original["checksum"] != corrected["checksum"]
    transition = api.post(
        f"/documents/{original['document_id']}/correct",
        json={
            "target_document_id": corrected["document_id"],
            "transition_reason": "explicit financial source correction custody",
        },
        headers=context_headers(offers[0]),
    )
    assert transition.status_code == 201, transition.text
    for offer, record in zip(offers, records, strict=True):
        route = f"/documents/{record['document_id']}"
        held = api.get(route, headers=context_headers(offer))
        assert held.status_code == 200
        assert (
            held.json()["composite_report_identity"]
            == offer["metadata"]["composite_report_identity"]
        )
        assert held.json()["report_revision_id"] == offer["metadata"]["report_revision_id"]
        download = api.get(route + "/download", headers=context_headers(offer))
        assert download.status_code == 200 and download.content == b64decode(
            offer["content_base64"]
        )
        assert (
            api.get(route + "/current", headers=context_headers(offer)).json()["document_id"]
            == corrected["document_id"]
        )
        assert api.get(route + "/retention", headers=context_headers(offer)).status_code == 200
        events = api.get(route + "/source-events", headers=context_headers(offer))
        assert events.status_code == 200
        assert (
            events.json()["events"][0]["report_revision_id"]
            == offer["metadata"]["report_revision_id"]
        )
        assert (
            events.json()["events"][0]["composite_report_identity"]
            == record["composite_report_identity"]
        )
        for suffix in ("", "/download", "/current", "/retention", "/source-events"):
            assert (
                api.get(
                    route + suffix, headers={**context_headers(offer), "X-Tenant-Id": "foreign"}
                ).status_code
                == 403
            )
    return records


def test_actual_handoffs_replay_correct_and_retain_original(client: ClientService) -> None:
    context_custody_journey(client)


@pytest.mark.parametrize("case", CASES[2:])
def test_optional_si_and_later_history_free_identity(client: ClientService, case: str) -> None:
    api, _ = client
    offer = context_payload(case)
    response = api.post("/documents", json=offer, headers=context_headers(offer, "lotus-render"))
    assert response.status_code == 201, response.text
    assert (
        response.json()["composite_report_identity"]
        == offer["metadata"]["composite_report_identity"]
    )


@pytest.mark.parametrize("change", ["context", "membership_digest", "product_digest", "revision"])
def test_conflicting_valid_replay_preserves_original(client: ClientService, change: str) -> None:
    api, _ = client
    offer = context_payload()
    original = api.post("/documents", json=offer, headers=context_headers(offer, "lotus-render"))
    assert original.status_code == 201, original.text
    changed = deepcopy(offer)
    identity = changed["metadata"]["composite_report_identity"]
    if change == "context":
        identity["source_context"]["since_inception"] = False
    elif change == "membership_digest":
        identity["source_context"]["memberships"][0]["response_digest"] = "sha256:" + "0" * 64
    elif change == "product_digest":
        product = identity["source_products"][0]
        product["source_response_digest"] = "sha256:" + "0" * 64
        product["pin"]["selection"]["response_digest"] = "sha256:" + "0" * 64
    else:
        changed["metadata"]["report_revision_id"] += "-changed"
    response = api.post("/documents", json=changed, headers=context_headers(offer, "lotus-render"))
    assert response.status_code == 409, response.text
    assert (
        api.get(
            f"/documents/{original.json()['document_id']}", headers=context_headers(offer)
        ).json()["composite_report_identity"]
        == offer["metadata"]["composite_report_identity"]
    )


def test_actual_artifact_false_declaration_refused(client: ClientService) -> None:
    api, _ = client
    offer = context_payload()
    offer["content_base64"] = context_payload("corrected")["content_base64"]
    response = api.post("/documents", json=offer, headers=context_headers(offer, "lotus-render"))
    assert response.status_code == 422, response.text
