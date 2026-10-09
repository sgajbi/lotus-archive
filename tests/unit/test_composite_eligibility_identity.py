"""Strict frozen Report selection, without Manage eligibility evaluation."""

from copy import deepcopy
import json
from pathlib import Path

from pydantic import TypeAdapter, ValidationError
import pytest

from app.archive.composite_products import CompositeCustodyIdentity
from app.archive.models import ArchiveDocumentInput
from app.archive.composite_eligibility import EligibilitySelection
from tests.fixtures.composite_eligibility import eligibility_identity, eligibility_payload


def test_v4_selection_schema_exactly_matches_frozen_producer_wire() -> None:
    frozen = (
        Path(__file__).resolve().parents[1] / "fixtures/composite_eligibility_selection.schema.json"
    )
    assert EligibilitySelection.model_json_schema() == json.loads(frozen.read_text())


def test_v4_explicit_month_gaps_are_preserved_without_filling_evidence() -> None:
    offered = eligibility_identity()
    other = deepcopy(offered["selection"]["months"][0])
    other["month"] = "2026-03"
    offered["selection"]["months"].append(other)
    offered["selection"]["period_end"] = "2026-03-31"
    assert (
        TypeAdapter(CompositeCustodyIdentity).validate_python(offered).model_dump(mode="json")
        == offered
    )


@pytest.mark.parametrize("kind", ["PUBLISHED", "EVALUATED_ONLY"])
def test_v4_frozen_identity_and_archive_scope_round_trip(kind: str) -> None:
    identity = eligibility_identity(kind)
    model: CompositeCustodyIdentity = TypeAdapter(CompositeCustodyIdentity).validate_python(
        identity
    )
    assert model.model_dump(mode="json") == identity
    metadata = eligibility_payload(kind)["metadata"]
    assert ArchiveDocumentInput.model_validate(metadata).model_dump(mode="json") == metadata


@pytest.mark.parametrize("kind", ["PUBLISHED", "EVALUATED_ONLY"])
@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "reversed",
        "missing",
        "extra",
        "start",
        "end",
        "month",
        "horizon",
        "reversed_period",
        "currency",
        "promotion",
        "fake_calculation",
        "hash",
        "unknown",
    ],
)
def test_v4_refuses_malformed_or_promoted_selection(kind: str, change: str) -> None:
    offered = deepcopy(eligibility_identity(kind))
    selection = offered["selection"]
    pin = selection["months"][0]
    if change == "duplicate":
        selection["months"].append(deepcopy(pin))
    elif change == "reversed":
        other = deepcopy(pin)
        other["month"] = "2025-12"
        selection["months"].append(other)
    elif change == "missing":
        del pin["proposal_content_hash"]
    elif change == "extra":
        pin["checker_approved"] = True
    elif change == "start":
        selection["period_start"] = "2026-01-02"
    elif change == "end":
        selection["period_end"] = "2026-01-30"
    elif change == "month":
        pin["month"] = "2026-13"
    elif change == "horizon":
        pin["month"] = "2026-02"
    elif change == "reversed_period":
        selection["period_start"] = "2026-02-01"
    elif change == "currency":
        selection["reporting_currency"] = "usd"
    elif change == "promotion":
        offered["publication_state"] = "ATTESTED"
    elif change == "fake_calculation":
        selection["calculation_id"] = "06310000-0000-4000-8000-000000000001"
    elif change == "hash":
        pin["proposal_content_hash"] = "0" * 64
    else:
        offered["source_products"] = []
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(offered)


@pytest.mark.parametrize("kind", ["PUBLISHED", "EVALUATED_ONLY"])
def test_v4_evidence_kinds_cannot_be_relabelled(kind: str) -> None:
    offered = eligibility_identity(kind)
    offered["selection"]["months"][0]["evidence_kind"] = (
        "EVALUATED_ONLY" if kind == "PUBLISHED" else "PUBLISHED"
    )
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(offered)


@pytest.mark.parametrize("sequence", [0, -1, True, "1"])
def test_v4_publication_sequence_is_a_positive_strict_integer(sequence: object) -> None:
    offered = eligibility_identity()
    offered["selection"]["months"][0]["publication_sequence"] = sequence
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(offered)


def test_v4_month_capacity_accepts_120_and_refuses_121() -> None:
    offered = eligibility_identity()
    selection = offered["selection"]
    prototype = selection["months"][0]
    selection["months"] = [
        {**prototype, "month": f"{2016 + index // 12:04}-{index % 12 + 1:02}"}
        for index in range(120)
    ]
    selection["period_start"] = "2016-01-01"
    selection["period_end"] = "2025-12-31"
    model: CompositeCustodyIdentity = TypeAdapter(CompositeCustodyIdentity).validate_python(offered)
    assert model.model_dump(mode="json") == offered
    selection["months"].append({**prototype, "month": "2026-01"})
    selection["period_end"] = "2026-01-31"
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(offered)
