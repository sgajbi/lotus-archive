from copy import deepcopy
from typing import Any

from pydantic import ValidationError
import pytest

from app.archive.models import ArchiveDocumentInput
from tests.fixtures.composite_custody import composite_metadata
from tests.fixtures.composite_workbook import workbook_bytes


@pytest.mark.parametrize(
    "field,value",
    [
        ("qualification", "OFFICIAL"),
        ("publication_state", "APPROVED"),
        ("series_digest", "bad"),
        ("control_revision", "invented"),
    ],
)
def test_summary_refuses_fabricated_authority_or_digest(field: str, value: str) -> None:
    metadata = composite_metadata(workbook_bytes())
    summary: Any = metadata["composite_report_identity"]
    summary[field] = value
    with pytest.raises(ValidationError):
        ArchiveDocumentInput.model_validate(metadata)


@pytest.mark.parametrize(
    "field,value",
    [
        ("tenant_id", "tenant-other"),
        ("composite_id", "other"),
        ("period_end", "2026-02-28"),
        ("return_view", "UNKNOWN"),
        ("response_digest", "bad"),
        ("windows", []),
    ],
)
def test_selection_must_match_exact_scope_and_horizon(field: str, value: object) -> None:
    metadata = composite_metadata(workbook_bytes())
    summary: Any = metadata["composite_report_identity"]
    summary["selection"][field] = value
    with pytest.raises(ValidationError):
        ArchiveDocumentInput.model_validate(metadata)


def test_vector_refuses_duplicate_gapped_or_blank_method_pins() -> None:
    metadata = composite_metadata(workbook_bytes())
    summary: Any = metadata["composite_report_identity"]
    pin = summary["selection"]["windows"][0]
    for windows in (
        [pin, deepcopy(pin)],
        [{**pin, "period_start": "2026-01-02"}],
        [{**pin, "method_binding": {"method_version": " "}}],
    ):
        summary["selection"]["windows"] = windows
        with pytest.raises(ValidationError):
            ArchiveDocumentInput.model_validate(metadata)


def test_composite_identity_round_trips_without_recomputation() -> None:
    metadata = composite_metadata(workbook_bytes())
    assert ArchiveDocumentInput.model_validate(metadata).model_dump(mode="json") == metadata


def test_window_date_order_and_contiguous_vector() -> None:
    metadata = composite_metadata(workbook_bytes())
    summary: Any = metadata["composite_report_identity"]
    original = deepcopy(summary["selection"]["windows"][0])
    summary["selection"]["windows"][0]["period_end"] = "2025-12-31"
    with pytest.raises(ValidationError):
        ArchiveDocumentInput.model_validate(metadata)
    second = {
        **original,
        "materialization_id": "00000000-0000-0000-0000-000000000002",
        "period_start": "2026-02-02",
        "period_end": "2026-02-28",
    }
    summary["selection"]["period_end"] = "2026-02-28"
    summary["selection"]["windows"] = [original, second]
    metadata["as_of_date"] = metadata["reporting_period_end"] = "2026-02-28"
    with pytest.raises(ValidationError):
        ArchiveDocumentInput.model_validate(metadata)
    second["period_start"] = "2026-02-01"
    assert (
        ArchiveDocumentInput.model_validate(metadata).reporting_period_end.isoformat()
        == "2026-02-28"
    )


def test_portfolio_family_cannot_launder_composite_summary() -> None:
    metadata = composite_metadata(workbook_bytes())
    metadata.update(
        report_type="portfolio_review",
        portfolio_scope="single_portfolio",
        portfolio_id="real-portfolio",
    )
    with pytest.raises(ValidationError):
        ArchiveDocumentInput.model_validate(metadata)
