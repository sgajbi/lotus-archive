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

    assert posture["implementedScope"] == "service_boundary_scaffold"
    assert posture["supportedArchiveFeatures"] == []

    unsupported_capabilities = posture["unsupportedProductCapabilities"]
    assert isinstance(unsupported_capabilities, list)

    unsupported = {item["capability"] for item in unsupported_capabilities}
    assert "generated_document_archival" in unsupported
    assert "controlled_document_retrieval" in unsupported
    assert "arbitrary_file_storage" in unsupported
    assert "manual_document_upload" in unsupported


def test_unsupported_capabilities_have_actionable_reasons() -> None:
    for item in UNSUPPORTED_PRODUCT_CAPABILITIES:
        assert item.capability
        assert item.reason
        assert "not implemented yet" in item.reason or "out of scope" in item.reason
