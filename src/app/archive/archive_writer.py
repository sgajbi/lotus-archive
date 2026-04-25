from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from app.archive.checksum import SUPPORTED_CHECKSUM_ALGORITHM, calculate_checksum
from app.archive.exceptions import DuplicateArchiveRequestConflict, MetadataValidationError
from app.archive.models import ArchiveDocumentInput, ArchiveDocumentMetadata
from app.archive.repository import ArchiveDocumentRepository
from app.archive.storage import ObjectStorage


class ArchiveWriter:
    def __init__(
        self,
        *,
        repository: ArchiveDocumentRepository,
        storage: ObjectStorage,
    ) -> None:
        self.repository = repository
        self.storage = storage

    def archive_document(
        self,
        *,
        metadata_input: ArchiveDocumentInput,
        content: bytes,
    ) -> ArchiveDocumentMetadata:
        checksum = calculate_checksum(content)
        existing = self.repository.get_by_archive_request_id(metadata_input.archive_request_id)
        if existing is not None:
            self._ensure_duplicate_request_is_idempotent(
                existing, metadata_input, checksum, content
            )
            return existing

        document_id = f"doc_{uuid4().hex}"
        storage_key = self._storage_key_for(metadata_input=metadata_input, document_id=document_id)
        stored_object = self.storage.put(
            key=storage_key,
            content=content,
            expected_checksum=checksum,
            checksum_algorithm=SUPPORTED_CHECKSUM_ALGORITHM,
        )
        now = datetime.now(timezone.utc)
        try:
            metadata = ArchiveDocumentMetadata(
                **metadata_input.model_dump(),
                document_id=document_id,
                storage_provider=stored_object.provider,
                storage_namespace=stored_object.namespace,
                storage_key=stored_object.key,
                checksum_algorithm=stored_object.checksum_algorithm,
                checksum=stored_object.checksum,
                size_bytes=stored_object.size_bytes,
                created_at=now,
                updated_at=now,
            )
        except ValidationError as exc:
            raise MetadataValidationError("archive metadata could not be validated") from exc
        return self.repository.save(metadata)

    def _ensure_duplicate_request_is_idempotent(
        self,
        existing: ArchiveDocumentMetadata,
        metadata_input: ArchiveDocumentInput,
        checksum: str,
        content: bytes,
    ) -> None:
        if existing.checksum != checksum or existing.size_bytes != len(content):
            raise DuplicateArchiveRequestConflict(
                "archive_request_id was reused with different document content"
            )
        comparable_existing = existing.model_dump(
            exclude={
                "document_id",
                "storage_provider",
                "storage_namespace",
                "storage_key",
                "checksum_algorithm",
                "checksum",
                "size_bytes",
                "purge_eligible_at",
                "purged_at",
                "purge_status",
                "legal_hold_status",
                "legal_hold_count",
                "supersedes_document_id",
                "superseded_by_document_id",
                "correction_of_document_id",
                "reissue_of_document_id",
                "created_at",
                "updated_at",
            }
        )
        if comparable_existing != metadata_input.model_dump():
            raise DuplicateArchiveRequestConflict(
                "archive_request_id was reused with different metadata"
            )

    def _storage_key_for(
        self,
        *,
        metadata_input: ArchiveDocumentInput,
        document_id: str,
    ) -> str:
        safe_output_format = metadata_input.output_format.lower().replace("/", "-")
        return "/".join(
            [
                metadata_input.region.lower(),
                metadata_input.tenant_id or "tenant-unspecified",
                metadata_input.report_type.lower(),
                f"{document_id}.{safe_output_format}",
            ]
        )
