from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArchiveModuleFamily:
    name: str
    responsibility: str
    source_of_truth: str


@dataclass(frozen=True)
class UnsupportedProductCapability:
    capability: str
    reason: str


ARCHIVE_MODULE_FAMILIES: tuple[ArchiveModuleFamily, ...] = (
    ArchiveModuleFamily(
        name="metadata",
        responsibility="archived document identity, source-backed metadata, and support-safe lookup",
        source_of_truth=(
            "lotus-archive metadata model; upstream references from lotus-report and lotus-render"
        ),
    ),
    ArchiveModuleFamily(
        name="storage",
        responsibility="object storage abstraction, checksum verification, and binary retrieval boundary",
        source_of_truth="lotus-archive storage adapter and checksum evidence",
    ),
    ArchiveModuleFamily(
        name="audit",
        responsibility="access and lifecycle audit records for archive reads and mutations",
        source_of_truth="lotus-archive access-audit model",
    ),
    ArchiveModuleFamily(
        name="retention",
        responsibility="retention policy assignment, purge eligibility, and support-safe purge evidence",
        source_of_truth="lotus-archive retention model",
    ),
    ArchiveModuleFamily(
        name="legal_hold",
        responsibility="legal hold set, release, authority reference, and purge blocking",
        source_of_truth="lotus-archive legal-hold model",
    ),
    ArchiveModuleFamily(
        name="lifecycle",
        responsibility="supersession, correction, reissue, and historical document relationships",
        source_of_truth="lotus-archive lifecycle relationship model",
    ),
)

UNSUPPORTED_PRODUCT_CAPABILITIES: tuple[UnsupportedProductCapability, ...] = (
    UnsupportedProductCapability(
        capability="document_lifecycle_relationships",
        reason="supersession, correction, and reissue APIs are not implemented yet",
    ),
    UnsupportedProductCapability(
        capability="gateway_backed_product_retrieval",
        reason="gateway facade is not implemented yet",
    ),
    UnsupportedProductCapability(
        capability="arbitrary_file_storage",
        reason="out of scope; lotus-archive is limited to Lotus-generated documents",
    ),
    UnsupportedProductCapability(
        capability="manual_document_upload",
        reason="out of scope for RFC-0103 first-wave archive support",
    ),
)


def service_posture() -> dict[str, object]:
    return {
        "implementedScope": "retention_purge_legal_hold_api",
        "supportedArchiveFeatures": [
            "generated_document_archival",
            "controlled_document_metadata_lookup",
            "controlled_document_binary_download",
            "access_audit_for_archive_api",
            "retention_policy_posture",
            "purge_eligibility_and_execution",
            "legal_hold_set_release_with_purge_blocking",
        ],
        "moduleFamilies": [
            {
                "name": module.name,
                "responsibility": module.responsibility,
                "sourceOfTruth": module.source_of_truth,
            }
            for module in ARCHIVE_MODULE_FAMILIES
        ],
        "unsupportedProductCapabilities": [
            {"capability": item.capability, "reason": item.reason}
            for item in UNSUPPORTED_PRODUCT_CAPABILITIES
        ],
    }
