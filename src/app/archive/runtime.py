from __future__ import annotations

from dataclasses import dataclass

from app.archive.archive_writer import ArchiveWriter
from app.archive.audit import AccessAuditRepository, InMemoryAccessAuditRepository
from app.archive.postgres_repository import (
    PostgresAccessAuditRepository,
    PostgresArchiveDocumentRepository,
)
from app.archive.repository import ArchiveDocumentRepository, InMemoryArchiveDocumentRepository
from app.archive.s3_storage import S3ObjectStorage
from app.archive.service import ArchiveDocumentService
from app.archive.settings import ArchiveRuntimeSettings
from app.archive.storage import FilesystemObjectStorage, ObjectStorage


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
    repository: ArchiveDocumentRepository
    audit_repository: AccessAuditRepository
    storage: ObjectStorage
    if settings.repository_mode == "postgresql":
        assert settings.database_url is not None
        repository = PostgresArchiveDocumentRepository(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
            statement_timeout_ms=settings.database_statement_timeout_ms,
        )
        audit_repository = PostgresAccessAuditRepository(
            settings.database_url,
            connect_timeout_seconds=settings.database_connect_timeout_seconds,
            statement_timeout_ms=settings.database_statement_timeout_ms,
        )
    else:
        repository = InMemoryArchiveDocumentRepository()
        audit_repository = InMemoryAccessAuditRepository()

    if settings.storage_mode == "s3":
        assert settings.s3_bucket is not None
        storage = S3ObjectStorage(
            bucket=settings.s3_bucket,
            namespace=settings.storage_namespace,
            key_prefix=settings.s3_key_prefix,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            server_side_encryption=settings.s3_server_side_encryption,
            kms_key_id=settings.s3_kms_key_id,
            connect_timeout_seconds=settings.s3_connect_timeout_seconds,
            read_timeout_seconds=settings.s3_read_timeout_seconds,
            max_attempts=settings.s3_max_attempts,
        )
    else:
        storage = FilesystemObjectStorage(
            settings.storage_root,
            namespace=settings.storage_namespace,
        )
    return ArchiveDocumentService(
        writer=ArchiveWriter(repository=repository, storage=storage),
        repository=repository,
        storage=storage,
        audit_repository=audit_repository,
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
