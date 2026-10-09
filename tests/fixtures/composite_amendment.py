"""Pinned producer selectors; synthetic identity digests and XLSX transport only."""

from base64 import b64encode
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from tests.fixtures.composite_custody import composite_metadata
from tests.fixtures.composite_workbook import workbook_bytes

SELECTIONS = json.loads(Path(__file__).with_name("composite_amendment_selections.json").read_text())


def amendment_payload(case: str = "v1-published", variant: str = "original") -> dict[str, Any]:
    content = workbook_bytes("Synthetic v6 custody transport " + case + ":" + variant)
    selection = deepcopy(SELECTIONS[case])
    identity = {
        "contract_version": "composite_review.v6",
        "qualification": "CONTROLLED_MONTHLY_SOURCE_AMENDMENT_REPLAY",
        "publication_state": "NOT_ATTESTED",
        "selection": selection,
        "series_digest": "a" * 64,
        "source_revision_digest": "b" * 64,
        "factual_content_digest": "c" * 64,
    }
    source_variant = "corrected" if variant == "corrected" else "original"
    if variant == "corrected":
        # Controlled Archive-only immutable metadata mutation, not producer amendment proof.
        identity["source_revision_digest"] = "d" * 64
        identity["selection"]["months"][0]["lineage_receipts"][0]["receipt_response_digest"] = (
            "sha256:" + "e" * 64
        )
    metadata = composite_metadata(content, "amendment-" + case + "-" + variant)
    metadata.update(
        tenant_id=selection["tenant_id"],
        composite_id=selection["composite_id"],
        region="APAC",
        as_of_date=selection["period_end"],
        reporting_period_start=selection["period_start"],
        reporting_period_end=selection["period_end"],
        template_version="v6",
        report_data_contract_version="composite_review.v6",
        composite_report_identity=identity,
        archive_request_id="synthetic-v6-" + case + "-" + variant,
        report_job_id="synthetic-v6-job-" + case + "-" + source_variant,
        snapshot_id="synthetic-v6-snapshot-" + case + "-" + source_variant,
        render_job_id="synthetic-v6-render-" + case + "-" + variant,
        report_revision_id="synthetic-v6-revision-" + case + "-" + source_variant,
    )
    return {"metadata": metadata, "content_base64": b64encode(content).decode("ascii")}
