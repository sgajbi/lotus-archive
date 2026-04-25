from app.archive.service_profile import (
    ARCHIVE_MODULE_FAMILIES,
    UNSUPPORTED_PRODUCT_CAPABILITIES,
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
        posture["implementedScope"] == "retention_purge_legal_hold_lifecycle_gateway_retrieval_api"
    )
    assert posture["supportedArchiveFeatures"] == [
        "generated_document_archival",
        "controlled_document_metadata_lookup",
        "controlled_document_binary_download",
        "access_audit_for_archive_api",
        "retention_policy_posture",
        "purge_eligibility_and_execution",
        "legal_hold_set_release_with_purge_blocking",
        "document_lifecycle_relationships",
        "current_document_resolution",
        "gateway_backed_document_retrieval",
    ]

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
