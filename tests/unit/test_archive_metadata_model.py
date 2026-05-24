from datetime import date

import pytest
from pydantic import ValidationError

from app.archive.models import ArchiveDocumentInput, DocumentClassification, GeneratedReportType
from app.archive.models import ArchiveDocumentMetadata


def valid_metadata_input(**overrides: object) -> ArchiveDocumentInput:
    values: dict[str, object] = {
        "archive_request_id": "archive-request-001",
        "report_job_id": "report-job-001",
        "report_request_id": "report-request-001",
        "snapshot_id": "snapshot-001",
        "render_job_id": "render-job-001",
        "render_attempt_id": "render-attempt-001",
        "report_type": "portfolio_review",
        "portfolio_scope": "single_portfolio",
        "portfolio_id": "PB_SG_GLOBAL_BAL_001",
        "client_reference": "client-ref-001",
        "as_of_date": date(2026, 4, 25),
        "reporting_period_start": date(2026, 1, 1),
        "reporting_period_end": date(2026, 3, 31),
        "frequency": "quarterly",
        "template_id": "portfolio-review",
        "template_version": "v1",
        "render_service_version": "0.1.0",
        "report_data_contract_version": "rfc-0101-v1",
        "mime_type": "application/pdf",
        "output_format": "pdf",
        "classification": DocumentClassification.CONFIDENTIAL,
        "region": "SG",
        "tenant_id": "tenant-private-bank",
        "retention_policy_id": "generated-report-standard",
        "retention_start_date": date(2026, 4, 25),
        "retain_until_date": date(2033, 4, 25),
        "created_by_service": "lotus-report",
        "created_by_actor": "report-worker",
    }
    values.update(overrides)
    return ArchiveDocumentInput.model_validate(values)


def reviewed_advisory_narrative_summary(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "package_id": "reviewed-narrative-package-001",
        "review_id": "narrative-review-001",
        "review_state": "APPROVED_FOR_ADVISOR_USE",
        "audience": "ADVISOR_REVIEW",
        "client_ready_status": "NOT_CLIENT_READY",
        "policy_version": "proposal-narrative-policy.v1",
        "source_narrative_hash": "sha256:" + "a" * 64,
        "report_data_narrative_hash": "sha256:" + "b" * 64,
        "guardrail_status": "PASSED",
        "section_count": 4,
        "disclosure_ref_count": 2,
        "limitation_count": 1,
        "included_in_render": True,
    }
    values.update(overrides)
    return values


def advisor_proposal_memo_summary(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "memo_id": "memo-001",
        "proposal_id": "proposal-001",
        "proposal_version_no": 1,
        "review_event_id": "memo-review-001",
        "review_action": "APPROVE_FOR_ADVISOR_USE",
        "client_ready_status": "BLOCKED",
        "memo_hash": "sha256:" + "c" * 64,
        "source_input_hash": "sha256:" + "d" * 64,
        "section_count": 8,
        "blocked_section_count": 2,
        "included_in_render": True,
    }
    values.update(overrides)
    return values


def test_metadata_input_accepts_source_backed_minimum_contract() -> None:
    metadata = valid_metadata_input()

    assert metadata.report_job_id == "report-job-001"
    assert metadata.report_type == GeneratedReportType.PORTFOLIO_REVIEW
    assert metadata.portfolio_id == "PB_SG_GLOBAL_BAL_001"
    assert metadata.classification == DocumentClassification.CONFIDENTIAL


def test_metadata_input_accepts_reviewed_advisory_narrative_archive_summary() -> None:
    metadata = valid_metadata_input(
        reviewed_advisory_narrative=reviewed_advisory_narrative_summary()
    )

    assert metadata.reviewed_advisory_narrative is not None
    assert metadata.reviewed_advisory_narrative.package_id == "reviewed-narrative-package-001"
    assert metadata.reviewed_advisory_narrative.review_state == "APPROVED_FOR_ADVISOR_USE"


def test_metadata_input_rejects_reviewed_narrative_for_non_portfolio_review() -> None:
    with pytest.raises(ValidationError):
        valid_metadata_input(
            report_type="proof_pack",
            reviewed_advisory_narrative=reviewed_advisory_narrative_summary(),
        )


def test_metadata_input_rejects_reviewed_narrative_for_non_portfolio_template() -> None:
    with pytest.raises(ValidationError):
        valid_metadata_input(
            template_id="proof-pack",
            reviewed_advisory_narrative=reviewed_advisory_narrative_summary(),
        )


def test_metadata_input_rejects_unrendered_reviewed_narrative_summary() -> None:
    with pytest.raises(ValidationError):
        valid_metadata_input(
            reviewed_advisory_narrative=reviewed_advisory_narrative_summary(
                included_in_render=False
            ),
        )


def test_metadata_input_rejects_client_ready_reviewed_narrative_summary() -> None:
    with pytest.raises(ValidationError):
        valid_metadata_input(
            reviewed_advisory_narrative=reviewed_advisory_narrative_summary(
                client_ready_status="CLIENT_READY"
            ),
        )


def test_metadata_input_rejects_reviewed_narrative_hash_without_sha256_lineage() -> None:
    with pytest.raises(ValidationError):
        valid_metadata_input(
            reviewed_advisory_narrative=reviewed_advisory_narrative_summary(
                source_narrative_hash="not-a-sha256-hash"
            ),
        )


def test_metadata_input_accepts_advisor_proposal_memo_archive_summary() -> None:
    metadata = valid_metadata_input(advisor_proposal_memo=advisor_proposal_memo_summary())

    assert metadata.advisor_proposal_memo is not None
    assert metadata.advisor_proposal_memo.memo_id == "memo-001"
    assert metadata.advisor_proposal_memo.review_action == "APPROVE_FOR_ADVISOR_USE"


def test_metadata_input_rejects_client_ready_advisor_proposal_memo_summary() -> None:
    with pytest.raises(ValidationError):
        valid_metadata_input(
            advisor_proposal_memo=advisor_proposal_memo_summary(client_ready_status="CLIENT_READY"),
        )


def test_metadata_input_rejects_unreviewed_advisor_proposal_memo_summary() -> None:
    with pytest.raises(ValidationError):
        valid_metadata_input(
            advisor_proposal_memo=advisor_proposal_memo_summary(review_action="REQUEST_CHANGES"),
        )


def test_metadata_input_rejects_advisor_proposal_memo_for_non_portfolio_review() -> None:
    with pytest.raises(ValidationError):
        valid_metadata_input(
            report_type="proof_pack",
            advisor_proposal_memo=advisor_proposal_memo_summary(),
        )


def test_metadata_input_accepts_proof_pack_report_type() -> None:
    metadata = valid_metadata_input(
        report_type="proof_pack",
        template_id="proof-pack",
        report_data_contract_version="dpm_proof_pack_report_input.v1",
    )

    assert metadata.report_type == GeneratedReportType.PROOF_PACK
    assert metadata.template_id == "proof-pack"


def test_metadata_input_accepts_rebalance_wave_report_type() -> None:
    metadata = valid_metadata_input(
        report_type="rebalance_wave",
        template_id="rebalance-wave",
        report_data_contract_version="dpm_wave_report_input.v1",
    )

    assert metadata.report_type == GeneratedReportType.REBALANCE_WAVE
    assert metadata.template_id == "rebalance-wave"


def test_metadata_input_rejects_unsupported_report_type() -> None:
    with pytest.raises(ValidationError):
        valid_metadata_input(report_type="manual_upload")


def test_metadata_input_rejects_reversed_reporting_period() -> None:
    with pytest.raises(ValidationError):
        valid_metadata_input(
            reporting_period_start=date(2026, 3, 31),
            reporting_period_end=date(2026, 1, 1),
        )


def test_metadata_input_requires_concrete_mime_type() -> None:
    with pytest.raises(ValidationError):
        valid_metadata_input(mime_type="pdf")


def test_metadata_input_rejects_reversed_retention_period() -> None:
    with pytest.raises(ValidationError):
        valid_metadata_input(
            retention_start_date=date(2033, 4, 25),
            retain_until_date=date(2026, 4, 25),
        )


def test_archive_metadata_requires_supported_checksum_algorithm() -> None:
    metadata_input = valid_metadata_input()

    with pytest.raises(ValidationError):
        ArchiveDocumentMetadata(
            **metadata_input.model_dump(),
            document_id="doc_test",
            storage_provider="filesystem",
            storage_namespace="local-development",
            storage_key="sg/tenant/report/doc.pdf",
            checksum_algorithm="md5",
            checksum="a" * 64,
            size_bytes=10,
        )
