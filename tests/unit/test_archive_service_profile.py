from app.archive.service_profile import (
    ARCHIVE_MODULE_FAMILIES,
    SUPPORTED_ARCHIVE_FEATURES,
    UNSUPPORTED_PRODUCT_CAPABILITIES,
    archive_supportability,
    service_posture,
)


def test_archive_module_families_are_explicit_and_unique() -> None:
    module_names = [module.name for module in ARCHIVE_MODULE_FAMILIES]

    assert module_names == [
        "metadata",
        "storage",
        "audit",
        "retention",
        "legal_hold",
        "lifecycle",
    ]
    assert len(module_names) == len(set(module_names))


def test_service_posture_does_not_overclaim_archive_features() -> None:
    posture = service_posture()

    assert (
        posture["implementedScope"]
        == "retention_purge_legal_hold_lifecycle_report_handoff_gateway_retrieval"
    )
    assert posture["supportedArchiveFeatures"] == list(SUPPORTED_ARCHIVE_FEATURES)

    unsupported_capabilities = posture["unsupportedProductCapabilities"]
    assert isinstance(unsupported_capabilities, list)

    unsupported = {item["capability"] for item in unsupported_capabilities}
    assert "workbench_document_retrieval_surface" in unsupported
    assert "gateway_backed_product_retrieval" not in unsupported
    assert "arbitrary_file_storage" in unsupported
    assert "manual_document_upload" in unsupported


def test_unsupported_capabilities_have_actionable_reasons() -> None:
    for item in UNSUPPORTED_PRODUCT_CAPABILITIES:
        assert item.capability
        assert item.reason
        assert "not implemented yet" in item.reason or "out of scope" in item.reason


def test_archive_supportability_reports_ready_posture_without_overclaiming_workbench() -> None:
    supportability = archive_supportability(is_draining=False)

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
    assert supportability["workbenchRetrievalSupported"] is False
    assert supportability["supportedArchiveFeatures"] == list(SUPPORTED_ARCHIVE_FEATURES)


def test_archive_supportability_reports_draining_degradation() -> None:
    supportability = archive_supportability(is_draining=True)

    assert supportability["state"] == "degraded"
    assert supportability["reason"] == "archive_supportability_draining"
    assert supportability["freshnessBucket"] == "current"
    assert supportability["draining"] is True
