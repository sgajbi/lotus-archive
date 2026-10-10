"""Exact producer selector fit and fail-closed historical custody axes."""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError
import pytest

from app.archive.composite_historical import HistoricalEligibilitySelection
from app.archive.composite_products import CompositeCustodyIdentity
from tests.fixtures.composite_historical import IDENTITIES, historical_payload


@pytest.mark.parametrize("case", IDENTITIES)
def test_all_report_graph_custody_identities_roundtrip(case: str) -> None:
    identity = historical_payload(case)["metadata"]["composite_report_identity"]
    assert (
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity).model_dump(mode="json")
        == identity
    )


def test_exact_report_selection_schema() -> None:
    frozen = (
        Path(__file__).resolve().parents[1] / "fixtures/composite_historical_selection.schema.json"
    )
    assert HistoricalEligibilitySelection.model_json_schema() == json.loads(frozen.read_text())


@pytest.mark.parametrize(
    "path,value",
    [
        (("publication_state",), "ATTESTED"),
        (("calculation_boundary",), "BANK_VERIFIED"),
        (("qualification",), "CONTROLLED_MONTHLY_SOURCE_AMENDMENT_REPLAY"),
        (("selection", "selection_version"), "v2"),
        (("selection", "selection_version"), None),
        (("selection", "months", 0, "product_version"), "v2"),
        (("selection", "months", 0, "product_version"), None),
        (("selection", "months", 0, "lineage_receipts"), []),
        (("selection", "months", 0, "lineage_receipts", 0, "product_version"), "v1"),
        (("selection", "months", 0, "lineage_receipts", 1, "product_version"), "v4"),
        (("selection", "months", 0, "parent_publication_response_digest"), None),
        (("selection", "months", 0, "receipt_content_hash"), "broken"),
        (("selection", "period_start"), "2026-09-02"),
    ],
)
def test_refuses_mixed_missing_or_promoted_identity(
    path: tuple[str | int, ...], value: Any
) -> None:
    identity = deepcopy(
        historical_payload("v2-correction-3-published")["metadata"]["composite_report_identity"]
    )
    cursor = identity
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity)


def test_root_refuses_correction_lineage_and_boundary_is_required() -> None:
    identity = historical_payload("v1-root-published")["metadata"]["composite_report_identity"]
    del identity["calculation_boundary"]
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity)
    identity = historical_payload("v1-root-published")["metadata"]["composite_report_identity"]
    identity["selection"]["months"][0]["lineage_receipts"] = []
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity)


@pytest.mark.parametrize("axis", ["months", "receipts", "unknown", "staged", "missing"])
def test_capacity_and_explicit_variant_refusal(axis: str) -> None:
    identity = historical_payload("v2-correction-3-published")["metadata"][
        "composite_report_identity"
    ]
    month = identity["selection"]["months"][0]
    if axis == "months":
        identity["selection"]["months"] *= 121
    elif axis == "receipts":
        month["lineage_receipts"] = (
            month["lineage_receipts"][:1] * 31 + month["lineage_receipts"][-1:]
        )
    elif axis == "unknown":
        month["product_version"] = "v99"
    elif axis == "staged":
        month["subject_revision"] = "staged-root"
    else:
        del month["product_version"]
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity)
