"""Fields that cross to a consumer must be validated where they are produced.

`lotus-idea` maps every lifecycle decision through
`ArchiveLifecycleDecisionEnvelope`, whose `residency_region` must match
`^[A-Z]{2,16}$` (`domain/data_lifecycle/archive_posture.py`). It refuses
anything else at contract mapping, *before* signature verification — so a
non-conforming value produces a decision the consumer cannot read at all, and
the failure surfaces at their end with nothing naming this service.

That constraint existed only in the consumer. Real documents carry values like
`SG`, so decisions conformed by convention rather than by enforcement, and the
first document archived with an AWS-style region would have emitted decisions
no consumer could map.

These assert the producer's half. They deliberately restate the consumer's rule
rather than importing it: this repository cannot import `lotus-idea`, and a
test that only checked "some pattern" would pass while diverging from the
contract it exists to hold.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.archive.idea_lifecycle_decisions.models import IdeaLifecycleDecision

#: What `lotus-idea` accepts. Copied deliberately, with its source named, so a
#: change on either side is visible here rather than at runtime.
CONSUMER_REGION_PATTERN = r"^[A-Z]{2,16}$"


def _payload(residency_region: str) -> dict[str, object]:
    issued = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
    return {
        "contract_version": "lotus-archive:IdeaEvidenceLifecycleDecision:v1",
        "decision_id": "dec-contract",
        "document_id": "doc-contract",
        "idea_evidence_pack_id": "pack-contract",
        "idea_candidate_id": "cand-contract",
        "source_correlation_ref": "src-contract",
        "tenant_id": "tenant-sg",
        "residency_region": residency_region,
        "retention_policy_id": "policy-1",
        "legal_hold_status": "clear",
        "legal_hold_count": 0,
        "purge_status": "not_eligible",
        "lifecycle_action": "RETAIN",
        "disposal_authorized": False,
        "decision_reason_code": "retained_by_policy",
        "authority": "lotus-archive",
        "issued_at_utc": issued.isoformat(),
        "expires_at_utc": (issued + timedelta(minutes=5)).isoformat(),
        "correlation_id": "corr-contract",
        "trace_id": "trace-contract",
        "signing_algorithm": "Ed25519",
        "signing_key_id": "managed-v1",
        "payload_digest": "sha256:contract",
        "signature": "ed25519:contract",
    }


def test_the_region_production_actually_uses_is_accepted() -> None:
    """`SG` is what archived documents carry, so the rule must not reject it.

    Without this, a stricter pattern would look correct and break every real
    decision.
    """
    decision = IdeaLifecycleDecision.model_validate(_payload("SG"))

    assert decision.residency_region == "SG"


@pytest.mark.parametrize(
    "residency_region",
    [
        "eu-west-1",  # the AWS-style form, which the consumer refuses
        "sg",  # lowercase
        "S",  # shorter than the consumer allows
        "SINGAPORE_REGION_FAR_TOO_LONG",  # longer than 16
        "SG ",  # trailing space
    ],
)
def test_a_region_the_consumer_would_refuse_is_refused_here(residency_region: str) -> None:
    """Refuse at issue, not at the consumer.

    Each of these maps to nothing in `lotus-idea`: the decision is rejected
    before verification, so the evidence is unusable and the error appears in
    a service that did not produce it.
    """
    with pytest.raises(ValidationError):
        IdeaLifecycleDecision.model_validate(_payload(residency_region))


def test_the_model_enforces_exactly_the_consumer_pattern() -> None:
    """The constraint is the consumer's, not one this service invented.

    Asserted against the schema rather than by behaviour so a divergence is
    named directly: if `lotus-idea` widens or narrows its rule, this fails and
    says which pattern moved.
    """
    schema = IdeaLifecycleDecision.model_json_schema()

    assert schema["properties"]["residency_region"]["pattern"] == CONSUMER_REGION_PATTERN
