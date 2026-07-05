from __future__ import annotations

from dataclasses import dataclass

from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import InMemoryAccessAuditRepository
from app.archive.exceptions import RuntimeConfigurationError
from app.archive.repository import InMemoryArchiveDocumentRepository
from app.archive.service import ArchiveDocumentService
from app.archive.settings import ArchiveRuntimeSettings
from app.archive.storage import FilesystemObjectStorage


@dataclass(frozen=True)
class ArchiveRuntimePosture:
    runtime_profile: str
    repository_mode: str
    storage_mode: str
    durable_metadata: bool
    durable_audit: bool
    durable_storage: bool
    state: str
    reason: str


def build_archive_service(settings: ArchiveRuntimeSettings) -> ArchiveDocumentService:
    if settings.repository_mode != "in-memory":
        raise RuntimeConfigurationError("PostgreSQL archive repository adapter is not available")
    if settings.storage_mode != "filesystem":
        raise RuntimeConfigurationError("S3 archive storage adapter is not available")

    repository = InMemoryArchiveDocumentRepository()
    storage = FilesystemObjectStorage(
        settings.storage_root,
        namespace=settings.storage_namespace,
    )
    return ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=InMemoryAccessAuditRepository(),
        max_decoded_document_bytes=settings.max_decoded_document_bytes,
    )


def runtime_posture(settings: ArchiveRuntimeSettings) -> ArchiveRuntimePosture:
    durable_metadata = settings.repository_mode == "postgresql"
    durable_storage = settings.storage_mode == "s3"
    local_profile = settings.runtime_profile in {"local-development", "test"}
    state = "ready" if durable_metadata and durable_storage else "degraded"
    reason = "durable_archive_runtime_configured"
    if local_profile:
        reason = "explicit_local_development_runtime"
    elif not durable_metadata or not durable_storage:
        state = "unavailable"
        reason = "durable_archive_runtime_missing"
    return ArchiveRuntimePosture(
        runtime_profile=settings.runtime_profile,
        repository_mode=settings.repository_mode,
        storage_mode=settings.storage_mode,
        durable_metadata=durable_metadata,
        durable_audit=durable_metadata,
        durable_storage=durable_storage,
        state=state,
        reason=reason,
    )
