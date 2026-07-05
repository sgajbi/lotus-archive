from __future__ import annotations

from dataclasses import dataclass

from app.archive.models import ArchiveDocumentInput


@dataclass(frozen=True)
class ArchiveDocumentCreateCommand:
    metadata: ArchiveDocumentInput
    content_base64: str


@dataclass(frozen=True)
class LegalHoldCreateCommand:
    hold_reason: str
    authority_reference: str


@dataclass(frozen=True)
class LifecycleTransitionCommand:
    target_document_id: str
    transition_reason: str
