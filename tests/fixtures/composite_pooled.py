"""Actual Report identity pins with synthetic OOXML component transport only."""

from base64 import b64encode
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from tests.fixtures.composite_custody import composite_metadata
from tests.fixtures.composite_workbook import workbook_bytes

IDENTITIES = json.loads(Path(__file__).with_name("composite_pooled_identities.json").read_text())
CASES = [
    "original",
    "technical",
    "corrected",
    "ambiguous",
    "elected_fallback",
    "one_sided",
    "work_limit",
    "zero",
]


def pooled_payload(case: str = "original") -> dict[str, Any]:
    content = workbook_bytes("Synthetic v5 custody transport: " + case)
    metadata = composite_metadata(content, "pooled-" + case)
    source_case = "original" if case == "technical" else case
    identity = deepcopy(IDENTITIES[source_case])
    scope = identity["selection"]
    metadata.update(
        tenant_id=scope["tenant_id"],
        composite_id=scope["composite_id"],
        region="APAC",
        as_of_date=scope["period_end"],
        reporting_period_start=scope["period_start"],
        reporting_period_end=scope["period_end"],
        template_version="v5",
        report_data_contract_version="composite_review.v5",
        composite_report_identity=identity,
        report_revision_id="synthetic-v5-revision-" + source_case,
        report_job_id="synthetic-v5-job-" + source_case,
        snapshot_id="synthetic-v5-snapshot-" + source_case,
    )
    return {"metadata": metadata, "content_base64": b64encode(content).decode("ascii")}
