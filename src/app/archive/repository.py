from __future__ import annotations

from typing import Protocol

from app.archive.exceptions import DuplicateArchiveRequestConflict
from app.archive.models import ArchiveDocumentMetadata


class ArchiveDocumentRepository(Protocol):
    def get_by_document_id(self, document_id: str) -> ArchiveDocumentMetadata | None: ...

    def get_by_archive_request_id(
        self,
        archive_request_id: str,
    ) -> ArchiveDocumentMetadata | None: ...

    def save(self, metadata: ArchiveDocumentMetadata) -> ArchiveDocumentMetadata: ...


class InMemoryArchiveDocumentRepository:
    def __init__(self) -> None:
        self._by_document_id: dict[str, ArchiveDocumentMetadata] = {}
        self._by_archive_request_id: dict[str, str] = {}

    def get_by_document_id(self, document_id: str) -> ArchiveDocumentMetadata | None:
        return self._by_document_id.get(document_id)

    def get_by_archive_request_id(
        self,
        archive_request_id: str,
    ) -> ArchiveDocumentMetadata | None:
        document_id = self._by_archive_request_id.get(archive_request_id)
        if document_id is None:
            return None
        return self._by_document_id[document_id]

    def save(self, metadata: ArchiveDocumentMetadata) -> ArchiveDocumentMetadata:
        existing_document_id = self._by_archive_request_id.get(metadata.archive_request_id)
        if existing_document_id and existing_document_id != metadata.document_id:
            raise DuplicateArchiveRequestConflict(
                "archive_request_id already belongs to another document"
            )
        self._by_document_id[metadata.document_id] = metadata
        self._by_archive_request_id[metadata.archive_request_id] = metadata.document_id
        return metadata
