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


class DeclaredChecksumMismatchError(ArchiveError):
    """The caller's declared artifact SHA-256 does not match what arrived.

    Custody is refused BEFORE anything is stored: persisting bytes whose
    declared and computed identities disagree would be corruption wearing a
    certificate. Both hashes are named so the operator sees exactly what the
    caller claimed and what Archive measured.
    """

    def __init__(self, *, declared: str, computed: str) -> None:
        self.declared = declared
        self.computed = computed
        super().__init__(f"declared artifact sha256 {declared} does not match computed {computed}")


class ArtifactIdentityCollisionError(ArchiveError):
    """The same exact bytes arrived under a different governed document
    reference. One artifact answers one governed question; a collision is an
    upstream identity fault worth surfacing, never a second custody record."""

    def __init__(self, *, checksum: str, existing_reference: str, offered_reference: str) -> None:
        self.checksum = checksum
        self.existing_reference = existing_reference
        self.offered_reference = offered_reference
        super().__init__(
            f"artifact {checksum} is already in custody under document reference "
            f"{existing_reference}; refusing re-custody under {offered_reference}"
        )


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
