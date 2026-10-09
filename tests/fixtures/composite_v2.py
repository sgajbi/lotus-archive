"""Frozen Report v2 custody context with synthetic transport bytes in local tests.

Source: Report417 shared-contract-r2, manifest SHA256
f0b3c41d829857605a7731faa6a0258d7f6ee4a39b661374a438612025eb99c4.
The JSON fixtures retain original/corrected source identities verbatim. These
component tests do not claim genuine rendered workbook or HTTP chain acceptance.
"""

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from tests.fixtures.composite_custody import composite_metadata


def v2_metadata(content: bytes, *, corrected: bool = False) -> dict[str, Any]:
    name = "financial_correction" if corrected else "original"
    source = json.loads(Path(__file__).with_name(f"composite_v2_{name}.json").read_text())
    metadata = composite_metadata(content, revision=f"v2-{name}")
    metadata.update(source)
    metadata.update(
        template_version="v2",
        report_data_contract_version="composite_review.v2",
        declared_artifact_sha256=sha256(content).hexdigest(),
    )
    return metadata
