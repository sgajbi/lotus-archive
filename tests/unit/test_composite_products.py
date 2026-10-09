from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError
import pytest

from app.archive.models import ArchiveDocumentInput
from tests.fixtures.composite_v2 import v2_metadata
from tests.fixtures.composite_custody import composite_metadata


def test_actual_retained_v1_r4_metadata_remains_admissible_without_relabelling() -> None:
    path = Path(__file__).parents[1] / "fixtures/composite_v1_retained_r4.json"
    retained = json.loads(path.read_text())
    offered = {
        key: value for key, value in retained.items() if key in ArchiveDocumentInput.model_fields
    }
    parsed = ArchiveDocumentInput.model_validate(offered)
    assert parsed.model_dump(mode="json") == offered


@pytest.mark.parametrize("corrected", [False, True])
def test_frozen_report_v2_retains_exact_ordered_identity(corrected: bool) -> None:
    metadata = v2_metadata(b"component transport", corrected=corrected)
    parsed = ArchiveDocumentInput.model_validate(metadata)
    assert (
        parsed.model_dump(mode="json")["composite_report_identity"]
        == metadata["composite_report_identity"]
    )


@pytest.mark.parametrize(
    "case",
    [
        "unknown_version",
        "mixed_template",
        "mixed_data",
        "empty",
        "nine",
        "duplicate",
        "unknown_identity",
        "unknown_product",
        "unknown_pin",
        "unknown_kind",
        "digest",
        "tenant_id",
        "composite_id",
        "reporting_currency",
        "return_view",
        "methodology",
        "engine_version",
        "year",
        "months",
        "strict_year",
        "strict_months",
        "reordered_windows",
        "changed_pin",
        "partial_month",
        "trailing_end",
        "approval",
    ],
)
def test_source_product_guard_rejects_incompatible_identity(case: str) -> None:
    metadata = v2_metadata(b"component transport")
    identity: Any = metadata["composite_report_identity"]
    products = identity["source_products"]
    calendar, trailing = products
    if case == "unknown_version":
        identity["contract_version"] = "composite_review.v3"
    elif case == "mixed_template":
        metadata["template_version"] = "v1"
    elif case == "mixed_data":
        metadata["report_data_contract_version"] = "composite_review.v1"
    elif case == "empty":
        identity["source_products"] = []
    elif case == "nine":
        identity["source_products"] = (products * 5)[:9]
    elif case == "duplicate":
        trailing["pin"]["product_key"] = calendar["pin"]["product_key"]
    elif case == "unknown_identity":
        identity["approval"] = "invented"
    elif case == "unknown_product":
        calendar["unknown"] = True
    elif case == "unknown_pin":
        calendar["pin"]["unknown"] = True
    elif case == "unknown_kind":
        calendar["pin"]["kind"] = "ARBITRARY"
    elif case == "digest":
        calendar["source_response_digest"] = "sha256:" + "0" * 64
    elif case in (
        "tenant_id",
        "composite_id",
        "reporting_currency",
        "return_view",
        "methodology",
        "engine_version",
    ):
        calendar["pin"]["selection"][case] = {
            "reporting_currency": "EUR",
            "return_view": "NET_ACTUAL",
        }.get(case, "other")
    elif case in ("year", "strict_year"):
        calendar["pin"]["year"] = 2021 if case == "year" else "2020"
    elif case in ("months", "strict_months"):
        trailing["pin"]["months"] = 11 if case == "months" else "12"
    elif case == "reordered_windows":
        calendar["pin"]["selection"]["windows"].reverse()
    elif case == "changed_pin":
        calendar["pin"]["selection"]["windows"][0]["source_cut_id"] = "altered"
    elif case == "partial_month":
        selection = calendar["pin"]["selection"]
        selection["windows"][0]["period_end"] = "2020-01-30"
        selection["windows"][1]["period_start"] = "2020-01-31"
    elif case == "trailing_end":
        selection = deepcopy(calendar["pin"]["selection"])
        trailing["pin"]["selection"] = selection
        trailing["source_response_digest"] = selection["response_digest"]
    elif case == "approval":
        identity["publication_state"] = "APPROVED"
    with pytest.raises(ValidationError):
        ArchiveDocumentInput.model_validate(metadata)


def test_product_order_is_retained_as_caller_identity() -> None:
    metadata = v2_metadata(b"component transport")
    identity: Any = metadata["composite_report_identity"]
    identity["source_products"].reverse()
    parsed = ArchiveDocumentInput.model_validate(metadata)
    assert parsed.model_dump(mode="json")["composite_report_identity"] == identity


@pytest.mark.parametrize(
    "identity_version,template_version,data_version",
    [(1, 1, 2), (1, 2, 1), (1, 2, 2), (2, 1, 1), (2, 1, 2), (2, 2, 1)],
)
def test_every_mixed_version_axis_refuses(
    identity_version: int, template_version: int, data_version: int
) -> None:
    metadata = (
        v2_metadata(b"component") if identity_version == 2 else composite_metadata(b"component")
    )
    metadata["template_version"] = f"v{template_version}"
    metadata["report_data_contract_version"] = f"composite_review.v{data_version}"
    with pytest.raises(ValidationError):
        ArchiveDocumentInput.model_validate(metadata)


@pytest.mark.parametrize("count", [1, 8])
def test_product_count_bounds_accept_valid_caller_selections(count: int) -> None:
    metadata = v2_metadata(b"component")
    identity: Any = metadata["composite_report_identity"]
    source = identity["source_products"][0]
    products = [deepcopy(source) for _ in range(count)]
    for index, product in enumerate(products):
        product["pin"]["product_key"] = f"calendar_2020_{index}"
    identity["source_products"] = products
    parsed = ArchiveDocumentInput.model_validate(metadata)
    assert parsed.model_dump(mode="json")["composite_report_identity"] == identity
