"""Exact supplier handoffs plus pinned optional identities; no producer rerun."""

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from tests.fixtures.composite_custody import composite_metadata
from tests.fixtures.composite_workbook import workbook_bytes

ROOT = Path(__file__).with_suffix("")
HANDOFF_PINS = {
    "original": "53e270dc2be6ed7459f4b519bace2a8b9366c0e2f02a29234b0a17b98d987c49",
    "corrected": "02f684dc4e057f6ed1a7c446339f7cb5d50d615185e9330e9dbc7ba5651e4986",
}
OPTIONAL = json.loads((ROOT / "optional_identities.json").read_bytes())
CASES = (*HANDOFF_PINS, *OPTIONAL)


def context_payload(case: str = "original") -> dict[str, Any]:
    if case in HANDOFF_PINS:
        raw = (ROOT / (case + ".handoff.json")).read_bytes()
        assert sha256(raw).hexdigest() == HANDOFF_PINS[case]
        offer: dict[str, Any] = json.loads(raw)
        return offer
    # Optional cases retain exact producer identities around synthetic XLSX
    # transport. They are component controls, not actual optional rendering.
    from base64 import b64encode

    identity = deepcopy(OPTIONAL[case])
    content = workbook_bytes("Synthetic optional-context custody " + case)
    metadata = composite_metadata(content, "source-context-" + case)
    selection = identity["selection"]
    metadata.update(
        tenant_id=selection["tenant_id"],
        composite_id=selection["composite_id"],
        as_of_date=selection["period_end"],
        reporting_period_start=selection["period_start"],
        reporting_period_end=selection["period_end"],
        template_version="v8",
        report_data_contract_version="composite_review.v8",
        composite_report_identity=identity,
    )
    return {"metadata": metadata, "content_base64": b64encode(content).decode()}
