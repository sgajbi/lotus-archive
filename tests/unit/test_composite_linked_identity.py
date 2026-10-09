"""Strict linked custody admission; controlled model fixtures, no live Report job."""

from copy import deepcopy
from datetime import date, timedelta
from uuid import UUID

from pydantic import TypeAdapter, ValidationError
import pytest

from app.archive.composite_products import CompositeCustodyIdentity
from app.archive.composite_linked import (
    CompositeLinkedRequest,
    CompositeLinkedRequestWithNullSequence,
)
from tests.fixtures.composite_linked import linked_identity, linked_payload


def test_linked_identity_preserves_exact_reviewed_wire_shape() -> None:
    offered = linked_identity()
    admitted: CompositeCustodyIdentity = TypeAdapter(CompositeCustodyIdentity).validate_python(
        offered
    )
    assert admitted.model_dump(mode="json") == offered


@pytest.mark.parametrize("corrected", [False, True])
def test_actual_report_r4_identity_round_trips_exactly(corrected: bool) -> None:
    offered = linked_payload(corrected=corrected)["metadata"]["composite_report_identity"]
    admitted: CompositeCustodyIdentity = TypeAdapter(CompositeCustodyIdentity).validate_python(
        offered
    )
    assert admitted.model_dump(mode="json") == offered
    assert admitted.model_dump()["selection"]["source_request"]["restatement_sequence"] is None


@pytest.mark.parametrize("mode", ["validation", "serialization"])
def test_linked_request_schema_keeps_strict_source_fields_in_both_directions(mode: str) -> None:
    from typing import Literal, cast

    schema = CompositeLinkedRequest.model_json_schema(
        mode=cast(Literal["validation", "serialization"], mode)
    )
    assert schema["additionalProperties"] is False
    assert "restatement_sequence" not in schema["properties"]
    assert set(schema["required"]) == set(linked_identity()["selection"]["source_request"])
    explicit_schema = CompositeLinkedRequestWithNullSequence.model_json_schema(
        mode=cast(Literal["validation", "serialization"], mode)
    )
    assert explicit_schema["additionalProperties"] is False
    assert explicit_schema["properties"]["restatement_sequence"]["type"] == "null"
    assert set(explicit_schema["required"]) == set(schema["required"]) | {"restatement_sequence"}


@pytest.mark.parametrize("value", [None, 1, 0, True, "1"])
def test_linked_request_preserves_null_presence_and_refuses_competing_sequence(
    value: object,
) -> None:
    offered = linked_identity()
    offered["selection"]["source_request"]["restatement_sequence"] = value
    if value is not None:
        with pytest.raises(ValidationError):
            TypeAdapter(CompositeCustodyIdentity).validate_python(offered)
    else:
        admitted: CompositeCustodyIdentity = TypeAdapter(CompositeCustodyIdentity).validate_python(
            offered
        )
        assert admitted.model_dump(mode="json") == offered
        assert admitted.model_dump()["selection"]["source_request"]["restatement_sequence"] is None


@pytest.mark.parametrize("count", [1, 120, 121])
def test_linked_vector_size_boundary(count: int) -> None:
    offered = linked_identity()
    selection = offered["selection"]
    windows = []
    for index in range(count):
        window = deepcopy(selection["windows"][0])
        window["materialization_id"] = str(UUID(int=index + 1))
        day = (date(2026, 1, 1) + timedelta(days=index)).isoformat()
        window["period_start"] = window["period_end"] = day
        windows.append(window)
    selection["windows"] = windows
    request = selection["source_request"]
    request["materialization_ids"] = [window["materialization_id"] for window in windows]
    request["period_start"] = windows[0]["period_start"]
    request["period_end"] = windows[-1]["period_end"]
    if count > 120:
        with pytest.raises(ValidationError):
            TypeAdapter(CompositeCustodyIdentity).validate_python(offered)
    else:
        assert (
            TypeAdapter(CompositeCustodyIdentity).validate_python(offered).model_dump(mode="json")
            == offered
        )


@pytest.mark.parametrize(
    "change",
    [
        "empty",
        "reordered",
        "duplicate",
        "ids_reordered",
        "ids_missing",
        "gap",
        "horizon",
        "metric",
        "method",
        "fee",
        "currency",
        "fingerprint",
        "digest",
        "missing_pin",
        "bool_sequence",
        "blank_binding",
        "products",
        "legacy_selection",
        "relabel",
        "approval",
        "unknown",
    ],
)
def test_linked_identity_refuses_incomplete_or_mixed_source_contract(change: str) -> None:
    offered = deepcopy(linked_identity())
    selection = offered["selection"]
    request = selection["source_request"]
    windows = selection["windows"]
    if change == "empty":
        selection["windows"] = []
    elif change == "reordered":
        windows.reverse()
    elif change == "duplicate":
        windows[1]["materialization_id"] = windows[0]["materialization_id"]
    elif change == "ids_reordered":
        request["materialization_ids"].reverse()
    elif change == "ids_missing":
        request["materialization_ids"].pop()
    elif change == "gap":
        windows[1]["period_start"] = "2026-02-02"
    elif change == "horizon":
        request["period_end"] = "2026-03-01"
    elif change in {"metric", "method", "fee", "currency"}:
        key = {
            "metric": "metric_id",
            "method": "method",
            "fee": "return_view",
            "currency": "reporting_currency",
        }[change]
        request[key] = "INVALID"
    elif change in {"fingerprint", "digest"}:
        selection["calculation_fingerprint" if change == "fingerprint" else "response_digest"] = (
            "bad"
        )
    elif change == "missing_pin":
        del windows[0]["attestation_content_hash"]
    elif change == "bool_sequence":
        windows[0]["restatement_sequence"] = True
    elif change == "blank_binding":
        windows[0]["method_binding"] = {"method": " "}
    elif change == "products":
        offered["source_products"] = []
    elif change == "legacy_selection":
        selection["composite_id"] = request["composite_id"]
    elif change == "relabel":
        offered["contract_version"] = "composite_review.v2"
    elif change == "approval":
        offered["publication_state"] = "APPROVED"
    else:
        request["unknown"] = "must not drop"
    with pytest.raises(ValidationError):
        TypeAdapter(CompositeCustodyIdentity).validate_python(offered)
