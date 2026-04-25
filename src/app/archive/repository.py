from __future__ import annotations

from typing import Protocol

from app.archive.exceptions import DuplicateArchiveRequestConflict
from app.archive.models import ArchiveDocumentMetadata, LegalHoldRecord


class ArchiveDocumentRepository(Protocol):
    def get_by_document_id(self, document_id: str) -> ArchiveDocumentMetadata | None: ...

    def get_by_archive_request_id(
        self,
        archive_request_id: str,
    ) -> ArchiveDocumentMetadata | None: ...

    def save(self, metadata: ArchiveDocumentMetadata) -> ArchiveDocumentMetadata: ...

    def save_legal_hold(self, legal_hold: LegalHoldRecord) -> LegalHoldRecord: ...

    def get_legal_hold(self, legal_hold_id: str) -> LegalHoldRecord | None: ...

    def list_legal_holds(self, document_id: str) -> list[LegalHoldRecord]: ...


class InMemoryArchiveDocumentRepository:
    def __init__(self) -> None:
        self._by_document_id: dict[str, ArchiveDocumentMetadata] = {}
        self._by_archive_request_id: dict[str, str] = {}
        self._legal_holds: dict[str, LegalHoldRecord] = {}

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

    def save_legal_hold(self, legal_hold: LegalHoldRecord) -> LegalHoldRecord:
        self._legal_holds[legal_hold.legal_hold_id] = legal_hold
        return legal_hold

    def get_legal_hold(self, legal_hold_id: str) -> LegalHoldRecord | None:
        return self._legal_holds.get(legal_hold_id)

    def list_legal_holds(self, document_id: str) -> list[LegalHoldRecord]:
        return [
            legal_hold
            for legal_hold in self._legal_holds.values()
            if legal_hold.document_id == document_id
        ]
