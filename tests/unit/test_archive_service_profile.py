from app.archive.service_profile import (
    ARCHIVE_MODULE_FAMILIES,
    SUPPORTED_ARCHIVE_FEATURES,
    UNSUPPORTED_PRODUCT_CAPABILITIES,
    archive_supportability,
    measured_unavailability_reason,
    service_posture,
)


def _supportability(**overrides: bool) -> dict[str, object]:
    readiness = {
        "is_draining": False,
        "repository_ready": True,
        "storage_ready": True,
        "access_audit_ready": True,
    }
    readiness.update(overrides)
    return archive_supportability(**readiness)


def test_archive_module_families_are_explicit_and_unique() -> None:
    module_names = [module.name for module in ARCHIVE_MODULE_FAMILIES]

    assert module_names == [
        "metadata",
        "storage",
        "audit",
        "retention",
        "legal_hold",
        "lifecycle",
        "source_events",
    ]
    assert len(module_names) == len(set(module_names))


def test_service_posture_does_not_overclaim_archive_features() -> None:
    posture = service_posture()

    assert (
        posture["implementedScope"]
        == "retention_purge_legal_hold_lifecycle_source_events_report_handoff_reviewed_narrative_advisor_memo_idea_evidence_gateway_workbench_retrieval"
    )
    assert posture["supportedArchiveFeatures"] == list(SUPPORTED_ARCHIVE_FEATURES)

    unsupported_capabilities = posture["unsupportedProductCapabilities"]
    assert isinstance(unsupported_capabilities, list)

    unsupported = {item["capability"] for item in unsupported_capabilities}
    assert "direct_workbench_archive_calls" in unsupported
    assert "gateway_backed_product_retrieval" not in unsupported
    assert "gateway_backed_workbench_document_retrieval" not in unsupported
    assert "arbitrary_file_storage" in unsupported
    assert "manual_document_upload" in unsupported


def test_unsupported_capabilities_have_actionable_reasons() -> None:
    for item in UNSUPPORTED_PRODUCT_CAPABILITIES:
        assert item.capability
        assert item.reason
        assert "out of scope" in item.reason


def test_archive_supportability_reports_ready_gateway_backed_workbench_posture() -> None:
    supportability = _supportability()

    assert supportability["featureKey"] == "archive.observability.archive_supportability"
    assert supportability["state"] == "ready"
    assert supportability["reason"] == "archive_supportability_ready"
    assert supportability["freshnessBucket"] == "current"
    assert supportability["retrievalSupported"] is True
    assert supportability["retentionSupported"] is True
    assert supportability["legalHoldSupported"] is True
    assert supportability["accessAuditSupported"] is True
    assert supportability["documentLifecycleSupported"] is True
    assert supportability["gatewayRetrievalSupported"] is True
    assert supportability["workbenchRetrievalSupported"] is True
    assert supportability["repositoryReady"] is True
    assert supportability["storageReady"] is True
    assert supportability["accessAuditReady"] is True
    supported_archive_features = supportability["supportedArchiveFeatures"]
    assert isinstance(supported_archive_features, list)
    assert supported_archive_features == list(SUPPORTED_ARCHIVE_FEATURES)
    assert "gateway_backed_workbench_document_retrieval" in supported_archive_features
    assert "archive_document_source_events" in supported_archive_features
    assert "reviewed_advisory_narrative_archive_summary" in supported_archive_features
    assert "advisor_proposal_memo_archive_summary" in supported_archive_features
    assert "idea_evidence_pack_archive_summary" in supported_archive_features


def test_archive_supportability_reports_draining_degradation() -> None:
    supportability = _supportability(is_draining=True)

    assert supportability["state"] == "degraded"
    assert supportability["reason"] == "archive_supportability_draining"
    assert supportability["freshnessBucket"] == "current"
    assert supportability["draining"] is True


def test_archive_supportability_reports_repository_unavailable() -> None:
    supportability = _supportability(repository_ready=False)

    assert supportability["state"] == "unavailable"
    assert supportability["reason"] == "archive_repository_unavailable"
    assert supportability["freshnessBucket"] == "unknown"
    assert supportability["retrievalSupported"] is False
    assert supportability["retentionSupported"] is False
    assert supportability["legalHoldSupported"] is False
    assert supportability["documentLifecycleSupported"] is False
    assert supportability["gatewayRetrievalSupported"] is False
    assert supportability["workbenchRetrievalSupported"] is False


def test_archive_supportability_reports_storage_unavailable() -> None:
    supportability = _supportability(storage_ready=False)

    assert supportability["state"] == "unavailable"
    assert supportability["reason"] == "archive_storage_unavailable"
    assert supportability["retrievalSupported"] is False
    assert supportability["retentionSupported"] is True
    assert supportability["legalHoldSupported"] is True
    assert supportability["documentLifecycleSupported"] is True
    assert supportability["gatewayRetrievalSupported"] is False
    assert supportability["workbenchRetrievalSupported"] is False


def test_archive_supportability_reports_access_audit_unavailable() -> None:
    supportability = _supportability(access_audit_ready=False)

    assert supportability["state"] == "unavailable"
    assert supportability["reason"] == "archive_access_audit_unavailable"
    assert supportability["accessAuditSupported"] is False
    assert supportability["retrievalSupported"] is True


def test_measured_unavailability_reason_orders_repository_before_storage_before_audit() -> None:
    assert (
        measured_unavailability_reason(
            repository_ready=False, storage_ready=False, access_audit_ready=False
        )
        == "archive_repository_unavailable"
    )
    assert (
        measured_unavailability_reason(
            repository_ready=True, storage_ready=False, access_audit_ready=False
        )
        == "archive_storage_unavailable"
    )
    assert (
        measured_unavailability_reason(
            repository_ready=True, storage_ready=True, access_audit_ready=False
        )
        == "archive_access_audit_unavailable"
    )
    assert (
        measured_unavailability_reason(
            repository_ready=True, storage_ready=True, access_audit_ready=True
        )
        is None
    )
