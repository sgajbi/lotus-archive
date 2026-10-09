"""Exact pinned Report DTO compatibility and refusal of false custody promotion."""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError
import pytest

from app.archive.composite_products import CompositeCustodyIdentity
from tests.fixtures.composite_amendment import SELECTIONS, amendment_payload


@pytest.mark.parametrize("case", SELECTIONS)
def test_pinned_monthly_amendment_selectors_are_preserved(case: str) -> None:
    identity = amendment_payload(case)["metadata"]["composite_report_identity"]
    assert (
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity).model_dump(mode="json")
        == identity
    )


def test_exact_report_amendment_selection_schema() -> None:
    from app.archive.composite_amendment import AmendmentEligibilitySelection

    frozen = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "fixtures/composite_amendment_selection.schema.json"
        ).read_text()
    )
    assert AmendmentEligibilitySelection.model_json_schema() == frozen


@pytest.mark.parametrize(
    "path,value",
    [
        (("publication_state",), "ATTESTED"),
        (("qualification",), "CONTROLLED_ELIGIBILITY_SOURCE_REPLAY"),
        (("contract_version",), "composite_review.v5"),
        (("selection", "selection_version"), "v1"),
        (("selection", "months", 0, "lineage_receipts"), []),
        (("selection", "months", 0, "lineage_receipts"), None),
        (("selection", "months", 0, "parent_publication_response_digest"), "broken"),
        (("selection", "months", 0, "lineage_receipts", 0, "product_version"), "v3"),
        (("selection", "months", 0, "lineage_receipts", 0, "receipt_response_digest"), "broken"),
        (("selection", "months", 0, "lineage_receipts", 0, "evaluation_revision"), ""),
        (("selection", "months", 0, "lineage_receipts", 0, "approval_content_hash"), None),
        (("selection", "months", 0, "lineage_receipts", 0, "bank_approved"), True),
        (("selection", "period_start"), "2026-09-02"),
        (("selection", "reporting_currency"), "usd"),
    ],
)
def test_refuses_invalid_source_axes_and_receipt_promotion(
    path: tuple[str | int, ...], value: Any
) -> None:
    identity = deepcopy(amendment_payload()["metadata"]["composite_report_identity"])
    cursor = identity
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity)


@pytest.mark.parametrize("case", SELECTIONS)
def test_required_lineage_fields_and_bounds(case: str) -> None:
    base = amendment_payload(case)["metadata"]["composite_report_identity"]
    for field in ("lineage_receipts",):
        identity = deepcopy(base)
        del identity["selection"]["months"][0][field]
        with pytest.raises(ValidationError):
            TypeAdapter(CompositeCustodyIdentity).validate_python(identity)
    identity = deepcopy(base)
    pin = identity["selection"]["months"][0]
    pin["lineage_receipts"] = pin["lineage_receipts"][:1] * 32
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity)
