from __future__ import annotations


class ArchiveError(Exception):
    """Base archive-domain exception."""


class MetadataValidationError(ArchiveError):
    pass


class DuplicateArchiveRequestConflict(ArchiveError):
    pass


class DocumentNotFoundError(ArchiveError):
    pass


class ArchiveDocumentLookupUnavailableError(ArchiveError):
    pass


class ArchiveDocumentLookupTimeoutError(ArchiveDocumentLookupUnavailableError):
    pass


class DocumentChecksumMismatchError(ArchiveError):
    pass


class LegalHoldActiveError(ArchiveError):
    pass


class LegalHoldNotFoundError(ArchiveError):
    pass


class PurgeNotEligibleError(ArchiveError):
    pass


class SupersessionConflictError(ArchiveError):
    pass


class UnsupportedLifecycleTransitionError(ArchiveError):
    pass


class HistoricalIntegrityError(ArchiveError):
    """A write attempted to change a field that is immutable after a document is archived."""


class StorageWriteFailedError(ArchiveError):
    pass


class StorageReadFailedError(ArchiveError):
    pass


class RuntimeConfigurationError(ArchiveError):
    pass
