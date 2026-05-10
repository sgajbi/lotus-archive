from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


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
    ArchiveModuleFamily(
        name="source_events",
        responsibility=(
            "support-safe generated-document and client-delivery lifecycle source events for "
            "downstream portfolio-memory consumers"
        ),
        source_of_truth="lotus-archive metadata and lifecycle relationship models",
    ),
)

SUPPORTED_ARCHIVE_FEATURES = (
    "generated_document_archival",
    "controlled_document_metadata_lookup",
    "controlled_document_binary_download",
    "access_audit_for_archive_api",
    "retention_policy_posture",
    "purge_eligibility_and_execution",
    "legal_hold_set_release_with_purge_blocking",
    "document_lifecycle_relationships",
    "current_document_resolution",
    "archive_document_source_events",
    "report_to_archive_handoff",
    "gateway_backed_document_retrieval",
    "gateway_backed_workbench_document_retrieval",
)

UNSUPPORTED_PRODUCT_CAPABILITIES: tuple[UnsupportedProductCapability, ...] = (
    UnsupportedProductCapability(
        capability="direct_workbench_archive_calls",
        reason="out of scope; Workbench retrieval must stay gateway-backed",
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

ArchiveSupportabilityState = Literal["ready", "degraded", "unavailable"]
ArchiveSupportabilityReason = Literal[
    "archive_supportability_ready",
    "archive_supportability_draining",
    "archive_capability_unavailable",
]
ArchiveSupportabilityFreshness = Literal["current", "unknown"]


def archive_supportability(*, is_draining: bool) -> dict[str, object]:
    supported_features = list(SUPPORTED_ARCHIVE_FEATURES)
    state: ArchiveSupportabilityState = "ready"
    reason: ArchiveSupportabilityReason = "archive_supportability_ready"
    freshness_bucket: ArchiveSupportabilityFreshness = "current"
    if is_draining:
        state = "degraded"
        reason = "archive_supportability_draining"
    elif not supported_features:
        state = "unavailable"
        reason = "archive_capability_unavailable"
        freshness_bucket = "unknown"

    return {
        "featureKey": "archive.observability.archive_supportability",
        "state": state,
        "reason": reason,
        "freshnessBucket": freshness_bucket,
        "retrievalSupported": True,
        "retentionSupported": True,
        "legalHoldSupported": True,
        "accessAuditSupported": True,
        "documentLifecycleSupported": True,
        "gatewayRetrievalSupported": True,
        "workbenchRetrievalSupported": True,
        "supportedArchiveFeatures": supported_features,
        "unsupportedProductCapabilities": [
            {"capability": item.capability, "reason": item.reason}
            for item in UNSUPPORTED_PRODUCT_CAPABILITIES
        ],
        "draining": is_draining,
    }


def service_posture() -> dict[str, object]:
    return {
        "implementedScope": "retention_purge_legal_hold_lifecycle_source_events_report_handoff_gateway_workbench_retrieval",
        "supportedArchiveFeatures": list(SUPPORTED_ARCHIVE_FEATURES),
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
