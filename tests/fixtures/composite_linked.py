"""Frozen actual Report r4 identities with synthetic component transport bytes.

Report417 r4 manifest: 036a775cdc0ac6dcc1533211fa80b6a9d6f2413f2397be2a931cbf9cb17a6c72.
Original/corrected context preserves actual Report job/snapshot/revision and
source pins. Archive/Render transport IDs and OOXML bytes are controlled test
values, never actual joined HTTP acceptance. The separate 9-key model fixture
uses r3 draft selection and explicit digest sentinels to prove absent-field shape.
"""

from base64 import b64encode
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from tests.fixtures.composite_custody import composite_metadata
from tests.fixtures.composite_workbook import workbook_bytes


def linked_identity() -> dict[str, Any]:
    selection = json.loads(Path(__file__).with_name("composite_linked_selection.json").read_text())
    return {
        "contract_version": "composite_review.v3",
        "qualification": "EXPLICIT_RETAINED_CALCULATED_REPLAY",
        "publication_state": "NOT_ATTESTED",
        "selection": selection,
        "series_digest": "1" * 64,
        "source_revision_digest": "2" * 64,
        "factual_content_digest": "3" * 64,
    }


def linked_payload(*, corrected: bool = False) -> dict[str, Any]:
    # Distinct synthetic content must not impersonate a retained v1/v2 artifact
    # under the actual r4 Report document reference.
    content = workbook_bytes(
        "component-linked-v3:4.04" if corrected else "component-linked-v3:3.02"
    )
    metadata = composite_metadata(
        content, "component-linked-corrected" if corrected else "component-linked-original"
    )
    name = "corrected" if corrected else "original"
    frozen = json.loads(Path(__file__).with_name(f"composite_linked_{name}.json").read_text())
    metadata.update(frozen)
    metadata.update(
        declared_artifact_sha256=sha256(content).hexdigest(),
    )
    return {"metadata": metadata, "content_base64": b64encode(content).decode("ascii")}
