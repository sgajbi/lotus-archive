"""Pinned Report r3 identities; synthetic XLSX custody, not joined delivery."""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from tests.fixtures.composite_amendment import amendment_payload

IDENTITIES = json.loads(
    Path(__file__).with_name("composite_historical_identities.json").read_text()
)


def historical_payload(case: str, variant: str = "original") -> dict[str, Any]:
    offer = amendment_payload("v1-published", variant)
    identity = deepcopy(IDENTITIES[case])
    metadata = offer["metadata"]
    metadata.update(
        composite_report_identity=identity,
        template_version="v7",
        report_data_contract_version="composite_review.v7",
    )
    for field in ("archive_request_id", "report_job_id", "snapshot_id", "render_job_id"):
        metadata[field] = "historical-" + case + "-" + variant + "-" + field
    metadata["report_revision_id"] = "historical-" + case
    return offer
