from __future__ import annotations


class ArchiveError(Exception):
    """Base archive-domain exception."""


class MetadataValidationError(ArchiveError):
    pass


class DuplicateArchiveRequestConflict(ArchiveError):
    pass


class DocumentNotFoundError(ArchiveError):
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


class StorageWriteFailedError(ArchiveError):
    pass


class StorageReadFailedError(ArchiveError):
    pass
