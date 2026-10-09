"""Exact producer-owned v5 selection and opaque seven-case custody identity."""

import json
from pathlib import Path
from typing import Any

from copy import deepcopy

from pydantic import TypeAdapter, ValidationError
import pytest

from app.archive.composite_products import CompositeCustodyIdentity
from app.archive.composite_pooled import PooledAnalysisSelection

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
IDENTITIES = json.loads((FIXTURES / "composite_pooled_identities.json").read_text())


def test_selector_schema_exactly_matches_report_owned_contract() -> None:
    frozen = json.loads((FIXTURES / "composite_pooled_selection.schema.json").read_text())
    assert PooledAnalysisSelection.model_json_schema() == frozen


@pytest.mark.parametrize(
    "path,value",
    [
        (("publication_state",), "ATTESTED"),
        (("qualification",), "CONTROLLED_ELIGIBILITY_SOURCE_REPLAY"),
        (("series_digest",), "sha256:" + "a" * 64),
        (("selection", "method"), "CARINO:v1"),
        (("selection", "metric_id"), "LINKED_MEMBER_CONTRIBUTION"),
        (("selection", "schema_version"), "composite-pooled-mwr.v2"),
        (("selection", "period_end"), "SAME_AS_START"),
        (("selection", "reporting_currency"), "usd"),
        (("selection", "fallback_policy"), "AUTOMATIC"),
        (("selection", "return_view"), "NET"),
        (("selection", "response_digest"), "a" * 64),
        (("selection", "expected_portfolio_ids"), []),
        (("selection", "source_pins"), []),
        (("selection", "source_pins", 0, "expected_page_count"), True),
        (("selection", "source_pins", 0, "expected_page_count"), 999),
        (("selection", "source_pins", 0, "completeness"), "PARTIAL"),
        (("selection", "source_pins", 0, "payload_digest"), "broken"),
        (("selection", "correction_of_calculation_id"), "00000000-0000-0000-0000-000000000001"),
        (("selection", "predecessor_response_digest"), "sha256:" + "a" * 64),
        (("selection", "bank_approved"), True),
        (("selection", "return_value"), 0),
    ],
)
def test_refuses_mutated_contract_or_financial_promotion(
    path: tuple[str | int, ...], value: object
) -> None:
    identity = deepcopy(IDENTITIES["original"])
    cursor = identity
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = identity["selection"]["period_start"] if value == "SAME_AS_START" else value
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity)


@pytest.mark.parametrize("field", ["expected_portfolio_ids", "source_pins"])
def test_refuses_duplicate_source_vectors(field: str) -> None:
    identity = deepcopy(IDENTITIES["original"])
    identity["selection"][field].append(deepcopy(identity["selection"][field][0]))
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity)


def test_refuses_self_correction_and_missing_required_null_pins() -> None:
    identity = deepcopy(IDENTITIES["corrected"])
    identity["selection"]["correction_of_calculation_id"] = identity["selection"]["calculation_id"]
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity)
    for key in ("correction_of_calculation_id", "predecessor_response_digest"):
        identity = deepcopy(IDENTITIES["original"])
        del identity["selection"][key]
        with pytest.raises(ValidationError):
            TypeAdapter(CompositeCustodyIdentity).validate_python(identity)


@pytest.mark.parametrize(
    "change", ["duplicate_pages", "reversed_coverage", "missing_pin", "missing_digest"]
)
def test_refuses_incomplete_source_provenance(change: str) -> None:
    identity = deepcopy(IDENTITIES["original"])
    pin = identity["selection"]["source_pins"][0]
    if change == "duplicate_pages":
        pin["page_ids"] *= 2
        pin["expected_page_count"] *= 2
    elif change == "reversed_coverage":
        pin["coverage_to"] = "2024-01-01"
    elif change == "missing_pin":
        del pin["source_cut_id"]
    else:
        del identity["selection"]["response_digest"]
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity)


@pytest.mark.parametrize("field,limit", [("expected_portfolio_ids", 10000), ("source_pins", 128)])
def test_source_vector_capacity_accepts_limit_and_refuses_overflow(field: str, limit: int) -> None:
    identity = deepcopy(IDENTITIES["original"])
    items: list[Any]
    if field == "expected_portfolio_ids":
        items = [f"member-{index}" for index in range(limit + 1)]
    else:
        items = [deepcopy(identity["selection"]["source_pins"][0]) for _ in range(limit + 1)]
        for index, pin in enumerate(items):
            pin["pin_id"] = f"pin-{index}"
    identity["selection"][field] = items[:limit]
    assert TypeAdapter(CompositeCustodyIdentity).validate_python(identity)
    identity["selection"][field] = items
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity)


@pytest.mark.parametrize("case", list(IDENTITIES))
def test_actual_report_worker_identity_preserved_without_derivation(case: str) -> None:
    identity = IDENTITIES[case]
    assert (
        TypeAdapter(CompositeCustodyIdentity).validate_python(identity).model_dump(mode="json")
        == identity
    )
