"""Pinned original/corrected custody and strict optional source-context joins."""

from copy import deepcopy
import json
from typing import Any

from pydantic import TypeAdapter, ValidationError
import pytest

from app.archive.api_models import ArchiveDocumentCreateRequest
from app.archive.composite_products import CompositeCustodyIdentity
from app.archive.composite_source_context import CompositeSourceContextSelection
from tests.fixtures.composite_source_context import CASES, ROOT, context_payload


@pytest.mark.parametrize("case", CASES)
def test_exact_supplier_identity_and_revision_roundtrip(case: str) -> None:
    offer = context_payload(case)
    request = ArchiveDocumentCreateRequest.model_validate(offer)
    assert request.metadata.composite_report_identity is not None
    assert (
        request.metadata.composite_report_identity.model_dump(mode="json")
        == offer["metadata"]["composite_report_identity"]
    )
    assert request.metadata.report_revision_id == offer["metadata"]["report_revision_id"]


def test_context_models_match_committed_report_schema() -> None:
    producer = json.loads((ROOT / "producer_context_schemas.json").read_bytes())
    actual = CompositeSourceContextSelection.model_json_schema()
    definitions = actual.pop("$defs")
    assert actual == producer["CompositeSourceContextSelection"]
    assert definitions["CompositeDefinitionPin"] == producer["CompositeDefinitionPin"]
    assert definitions["CompositeMembershipPin"] == producer["CompositeMembershipPin"]


@pytest.mark.parametrize(
    "path,value",
    [
        (("contract_version",), "composite_review.v9"),
        (("qualification",), "BANK_APPROVED"),
        (("publication_state",), "ATTESTED"),
        (("source_context",), None),
        (("source_context", "since_inception"), "true"),
        (("source_context", "definition", "definition_version"), "other"),
        (("source_context", "memberships"), None),
        (("source_context", "memberships", 0, "content_hash"), "sha256:" + "0" * 64),
        (("source_context", "memberships", 0, "response_digest"), "broken"),
        (("definition", "source_response_digest"), "sha256:" + "0" * 64),
        (("definition", "pin", "content_hash"), None),
        (("definition", "pin", "bank_approved"), True),
        (("selection", "windows", 0, "definition_content_hash"), "sha256:" + "0" * 64),
        (("selection", "windows", 0, "membership_content_hash"), "sha256:" + "0" * 64),
        (("selection", "windows", 0, "period_start"), "2026-01-02"),
        (("source_products",), None),
        (("source_products", 0, "source_response_digest"), "sha256:" + "0" * 64),
        (("source_products", 0, "pin", "kind"), "ANNUAL_RETURN"),
        (("source_products", 0, "pin", "selection", "tenant_id"), "foreign"),
        (("source_products", 0, "pin", "selection", "composite_id"), "foreign"),
        (("source_products", 0, "pin", "selection", "reporting_currency"), "EUR"),
        (("source_products", 0, "pin", "selection", "return_view"), "GROSS"),
        (("source_products", 0, "pin", "selection", "methodology"), "other"),
        (("source_products", 0, "pin", "selection", "engine_version"), "other"),
        (("source_products", 0, "pin", "year"), 2025),
        (("source_products", 1, "pin", "months"), 3),
    ],
)
def test_refuses_false_context_or_product_join(path: tuple[str | int, ...], value: Any) -> None:
    identity = deepcopy(context_payload()["metadata"]["composite_report_identity"])
    cursor = identity
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity)


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate_membership",
        "excess_memberships",
        "duplicate_product",
        "excess_products",
        "missing_definition",
        "empty_attachments",
        "definition_window_mismatch",
        "extra_context",
    ],
)
def test_required_unique_bounded_context(failure: str) -> None:
    identity = context_payload()["metadata"]["composite_report_identity"]
    context = identity["source_context"]
    if failure == "duplicate_membership":
        context["memberships"] *= 2
    elif failure == "excess_memberships":
        context["memberships"] *= 3
    elif failure == "duplicate_product":
        identity["source_products"].append(deepcopy(identity["source_products"][0]))
    elif failure == "excess_products":
        identity["source_products"] *= 5
    elif failure == "missing_definition":
        del identity["definition"]
    elif failure == "empty_attachments":
        context.update(since_inception=False, memberships=[])
    elif failure == "definition_window_mismatch":
        identity["definition"]["pin"]["content_hash"] = "sha256:" + "0" * 64
        context["definition"]["content_hash"] = "sha256:" + "0" * 64
    else:
        context["approval"] = "caller-injected"
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "foreign"),
        ("composite_id", "foreign"),
        ("template_version", "v7"),
        ("report_data_contract_version", "composite_review.v7"),
        ("as_of_date", "2026-12-30"),
        ("reporting_period_start", "2026-02-01"),
        ("reporting_period_end", "2026-11-30"),
    ],
)
def test_outer_archive_scope_and_template_must_agree(field: str, value: str) -> None:
    offer = context_payload()
    offer["metadata"][field] = value
    with pytest.raises(ValidationError):
        ArchiveDocumentCreateRequest.model_validate(offer)
