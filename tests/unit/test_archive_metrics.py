from datetime import date

import pytest

import app.archive.metrics as archive_metrics
from app.archive.models import (
    ArchiveDocumentMetadata,
    DocumentClassification,
    LegalHoldRecord,
    LegalHoldStatus,
)
from app.archive.metrics import (
    ARCHIVE_METRIC_CONTRACTS,
    FORBIDDEN_METRIC_LABELS,
    IMPLEMENTED_ARCHIVE_OPERATIONS,
    ArchiveMetricContract,
    record_archive_document_size,
    record_archive_operation,
    record_archive_supportability,
    validate_archive_metric_contracts,
)


def test_archive_metric_contracts_are_bounded_and_implementation_truthful() -> None:
    validate_archive_metric_contracts()

    implemented_names = {
        contract.name for contract in ARCHIVE_METRIC_CONTRACTS if contract.implemented
    }
    assert {
        "lotus_archive_operations_total",
        "lotus_archive_operation_duration_seconds",
        "lotus_archive_document_size_bytes",
        "lotus_archive_supportability_total",
    } <= implemented_names
    assert {
        "archive_create",
        "metadata_lookup",
        "binary_download",
        "retention_lookup",
        "purge_execution",
        "legal_hold_set",
        "lifecycle_supersede",
    } <= IMPLEMENTED_ARCHIVE_OPERATIONS
    for contract in ARCHIVE_METRIC_CONTRACTS:
        assert not (set(contract.labels) & FORBIDDEN_METRIC_LABELS)
        assert "document_id" not in contract.labels
        assert "report_job_id" not in contract.labels
        assert "render_job_id" not in contract.labels
        assert "correlation_id" not in contract.labels
        assert "trace_id" not in contract.labels
        assert "storage_key" not in contract.labels


def test_archive_metric_contract_validation_rejects_duplicate_metric_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duplicate_contracts = ARCHIVE_METRIC_CONTRACTS + (ARCHIVE_METRIC_CONTRACTS[0],)
    monkeypatch.setattr(archive_metrics, "ARCHIVE_METRIC_CONTRACTS", duplicate_contracts)

    with pytest.raises(ValueError, match="duplicate_archive_metric_name"):
        validate_archive_metric_contracts()


def test_archive_metric_contract_validation_rejects_forbidden_and_unsupported_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forbidden_label_contract = ArchiveMetricContract(
        name="lotus_archive_invalid_forbidden_label_total",
        metric_type="counter",
        labels=("operation", "document_id"),
        implemented=True,
        description="invalid high-cardinality label",
    )
    monkeypatch.setattr(
        archive_metrics,
        "ARCHIVE_METRIC_CONTRACTS",
        (forbidden_label_contract,),
    )

    with pytest.raises(ValueError, match="forbidden_archive_metric_label:document_id"):
        validate_archive_metric_contracts()

    unsupported_label_contract = ArchiveMetricContract(
        name="lotus_archive_invalid_unsupported_label_total",
        metric_type="counter",
        labels=("operation", "storage_provider"),
        implemented=True,
        description="invalid non-contract label",
    )
    monkeypatch.setattr(
        archive_metrics,
        "ARCHIVE_METRIC_CONTRACTS",
        (unsupported_label_contract,),
    )

    with pytest.raises(ValueError, match="unsupported_archive_metric_label:storage_provider"):
        validate_archive_metric_contracts()


def test_record_archive_operation_rejects_unknown_operation() -> None:
    with pytest.raises(ValueError, match="unsupported_archive_metric_operation"):
        record_archive_operation(operation="manual_upload", status="failed")


def test_record_archive_operation_bounds_status_failure_category_and_duration() -> None:
    record_archive_operation(
        operation="archive_create",
        status="archived",
        duration_seconds=0.01,
    )
    record_archive_operation(
        operation="metadata_lookup",
        status="not-a-contract-status",
        failure_category=" Document-Not-Found ",
        duration_seconds=-1.0,
    )
    record_archive_operation(
        operation="binary_download",
        status="failed",
        failure_category="",
    )
    record_archive_operation(
        operation="binary_download",
        status="failed",
        failure_category="   ",
    )
    record_archive_operation(
        operation="purge_execution",
        status="failed",
        failure_category="storage failed!",
    )
    record_archive_operation(
        operation="purge_execution",
        status="failed",
        failure_category="x" * 81,
    )


def test_record_archive_document_size_clamps_counts_and_ignores_missing_size() -> None:
    record_archive_document_size(status="archived", size_bytes=2048)
    record_archive_document_size(status="archived", size_bytes=-1)
    record_archive_document_size(status="not-a-contract-status", size_bytes=1)
    record_archive_document_size(status="archived", size_bytes=None)


def test_record_archive_supportability_bounds_state_reason_and_freshness() -> None:
    record_archive_supportability(
        state="ready",
        reason="archive_supportability_ready",
        freshness_bucket="current",
    )
    record_archive_supportability(
        state="not-a-contract-state",
        reason="not-a-contract-reason",
        freshness_bucket="not-a-contract-freshness",
    )


def test_status_derivation_uses_operation_contracts() -> None:
    metadata = ArchiveDocumentMetadata(
        archive_request_id="arch-1",
        report_job_id="rjob-1",
        report_request_id="rrq-1",
        snapshot_id="rsnap-1",
        render_job_id="rdr-1",
        render_attempt_id="rdr-1",
        report_type="portfolio_review",
        portfolio_scope='{"portfolio_ids":["PB_SG_GLOBAL_BAL_001"]}',
        portfolio_id="PB_SG_GLOBAL_BAL_001",
        client_reference="client-ref-001",
        as_of_date=date(2026, 4, 22),
        reporting_period_start=date(2026, 1, 1),
        reporting_period_end=date(2026, 4, 22),
        frequency="ad_hoc",
        template_id="portfolio-review",
        template_version="v1",
        render_service_version="0.14.2",
        report_data_contract_version="v1",
        mime_type="application/pdf",
        output_format="pdf",
        classification=DocumentClassification.CONFIDENTIAL,
        region="APAC",
        tenant_id="tenant-sg",
        retention_start_date=date(2026, 4, 22),
        created_by_service="lotus-report",
        created_by_actor="advisor-123",
        document_id="doc-1",
        storage_provider="filesystem",
        storage_namespace="archive",
        storage_key="documents/doc-1.pdf",
        checksum="a" * 64,
        size_bytes=2048,
    )
    hold = LegalHoldRecord(
        legal_hold_id="hold-1",
        document_id="doc-1",
        hold_status=LegalHoldStatus.ACTIVE,
        hold_reason="regulatory",
        authority_reference="case-1",
        requested_by="operator-123",
    )

    assert archive_metrics._status_from_result("archive_create", metadata) == "archived"
    assert archive_metrics._status_from_result("retention_lookup", metadata) == "clear"
    assert archive_metrics._status_from_result("legal_hold_set", hold) == "active"
