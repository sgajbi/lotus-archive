"""Controlled custody model/transport fixtures, never actual Manage authority."""

from base64 import b64encode
from typing import Any

from app.archive.checksum import calculate_checksum
from tests.fixtures.composite_custody import composite_metadata
from tests.fixtures.composite_workbook import workbook_bytes


def eligibility_identity(kind: str = "PUBLISHED") -> dict[str, Any]:
    pin: dict[str, Any] = {
        "evidence_kind": kind,
        "month": "2026-01",
        "evaluation_revision": "synthetic.evaluation.r1",
        "proposal_content_hash": "sha256:" + "1" * 64,
        "parent_membership_revision": "synthetic.parent.r1",
        "parent_membership_content_hash": "sha256:" + "2" * 64,
        "source_cut_id": "synthetic-cut",
    }
    if kind == "EVALUATED_ONLY":
        pin["proposal_response_digest"] = "sha256:" + "3" * 64
    else:
        pin.update(
            approval_content_hash="sha256:" + "3" * 64,
            receipt_content_hash="sha256:" + "4" * 64,
            receipt_response_digest="sha256:" + "5" * 64,
            membership_revision="synthetic.membership.r1",
            membership_content_hash="sha256:" + "6" * 64,
            membership_response_digest="sha256:" + "7" * 64,
            attestation_version="synthetic.attestation.r1",
            universe_content_hash="sha256:" + "8" * 64,
            universe_response_digest="sha256:" + "9" * 64,
            parent_response_digest="sha256:" + "a" * 64,
            publication_sequence=1,
            publication_response_digest="sha256:" + "b" * 64,
        )
    return {
        "contract_version": "composite_review.v4",
        "qualification": "CONTROLLED_ELIGIBILITY_SOURCE_REPLAY",
        "publication_state": "NOT_ATTESTED",
        "selection": {
            "tenant_id": "synthetic-tenant-a",
            "composite_id": "SYNTHETIC_ELIGIBILITY_USD",
            "definition_version": "synthetic.definition.r1",
            "reporting_currency": "USD",
            "period_start": "2026-01-01",
            "period_end": "2026-01-31",
            "months": [pin],
        },
        "series_digest": "c" * 64,
        "source_revision_digest": "d" * 64,
        "factual_content_digest": "e" * 64,
    }


def eligibility_payload(kind: str = "PUBLISHED", variant: str = "original") -> dict[str, Any]:
    content = workbook_bytes("Synthetic v4 custody transport " + kind + ":" + variant)
    metadata = composite_metadata(content, "eligibility-" + kind + "-" + variant)
    identity = eligibility_identity(kind)
    scope = identity["selection"]
    source_variant = "corrected" if variant == "corrected" else "original"
    if variant == "corrected":
        identity["source_revision_digest"] = "f" * 64
        identity["factual_content_digest"] = "0" * 64
        identity["selection"]["months"][0]["proposal_content_hash"] = "sha256:" + "d" * 64
    metadata.update(
        composite_id=scope["composite_id"],
        tenant_id=scope["tenant_id"],
        region="APAC",
        as_of_date=scope["period_end"],
        reporting_period_start=scope["period_start"],
        reporting_period_end=scope["period_end"],
        template_version="v4",
        report_data_contract_version="composite_review.v4",
        composite_report_identity=identity,
        archive_request_id="synthetic-v4-" + kind + "-" + variant,
        report_job_id="synthetic-v4-job-" + kind + "-" + source_variant,
        snapshot_id="synthetic-v4-snapshot-" + kind + "-" + source_variant,
        render_job_id="synthetic-v4-render-" + kind + "-" + variant,
        document_reference="synthetic-v4-document-" + kind + "-" + variant,
        report_revision_id="synthetic-v4-revision-" + kind + "-" + source_variant,
    )
    metadata["declared_artifact_sha256"] = calculate_checksum(content)
    return {"metadata": metadata, "content_base64": b64encode(content).decode("ascii")}
