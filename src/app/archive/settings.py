from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64DecodeError
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.archive.exceptions import RuntimeConfigurationError
from app.archive.idea_lifecycle_decisions.signing import RetainedVerificationKey

ArchiveRuntimeProfile = Literal["local-development", "test", "production"]
ArchiveRepositoryMode = Literal["in-memory", "postgresql"]
ArchiveStorageMode = Literal["filesystem", "s3"]
S3ServerSideEncryption = Literal["AES256", "aws:kms"]


class ArchiveRuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOTUS_ARCHIVE_", extra="ignore")

    runtime_profile: ArchiveRuntimeProfile = Field(default="local-development")
    repository_mode: ArchiveRepositoryMode = Field(default="in-memory")
    storage_mode: ArchiveStorageMode = Field(default="filesystem")
    storage_root: Path = Field(
        default_factory=lambda: Path(tempfile.gettempdir()) / "lotus-archive-objects"
    )
    storage_namespace: str = Field(default="local-development", min_length=1)
    database_url: str | None = Field(default=None)
    database_connect_timeout_seconds: int = Field(default=5, ge=1, le=60)
    database_statement_timeout_ms: int = Field(default=30_000, ge=100, le=600_000)
    database_pool_min_size: int = Field(default=1, ge=0, le=10)
    database_pool_max_size: int = Field(default=10, ge=1, le=50)
    s3_bucket: str | None = Field(default=None, min_length=3)
    s3_key_prefix: str = Field(default="archive", min_length=1)
    s3_region: str | None = Field(default=None, min_length=1)
    s3_endpoint_url: str | None = Field(default=None, min_length=1)
    s3_server_side_encryption: S3ServerSideEncryption = Field(default="AES256")
    s3_kms_key_id: str | None = Field(default=None, min_length=1)
    s3_connect_timeout_seconds: float = Field(default=5.0, gt=0.0, le=60.0)
    s3_read_timeout_seconds: float = Field(default=30.0, gt=0.0, le=300.0)
    s3_max_attempts: int = Field(default=3, ge=1, le=10)
    max_decoded_document_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    idea_lifecycle_decision_ledger_path: Path = Field(
        default_factory=lambda: (
            Path(tempfile.gettempdir()) / "lotus-archive-idea-lifecycle-decisions.sqlite3"
        )
    )
    idea_lifecycle_decision_private_key_base64: SecretStr = Field(default=SecretStr(""))
    idea_lifecycle_decision_signing_key_id: str = Field(default="ephemeral-local-v1", min_length=3)
    #: When the active signing key began signing. Required outside the local
    #: profile: a consumer selects a verification key by the decision's issue
    #: time, and a defaulted window is the invented one this exists to prevent.
    idea_lifecycle_decision_signing_key_not_before_utc: datetime | None = Field(default=None)
    #: Keys that have stopped signing but must stay published, as JSON:
    #: [{"key_id", "public_key_base64", "not_before_utc", "not_after_utc"}].
    #: Public keys are not secrets; each entry needs a closed window, since a
    #: rotated key trusted without an end never stops being accepted.
    idea_lifecycle_decision_retained_verification_keys: str = Field(default="")
    #: Key IDs whose signatures are withdrawn, as a JSON list of strings.
    #:
    #: Separate from the retained list, and keyed by ID rather than carrying a
    #: status on each entry, because revocation is not a property of retirement.
    #: The key that is *still signing* can be compromised, and it has no closed
    #: window to be listed under -- so a status field on the retained entries
    #: could not express the case that matters most. Listing the active signer
    #: here stops it signing and publishes it as revoked, which is the pair of
    #: effects revocation means.
    idea_lifecycle_decision_revoked_key_ids: str = Field(default="")

    @model_validator(mode="after")
    def validate_runtime_posture(self) -> ArchiveRuntimeSettings:
        if self.database_pool_min_size > self.database_pool_max_size:
            raise RuntimeConfigurationError("database pool min size cannot exceed max size")
        local_profile = self.runtime_profile in {"local-development", "test"}
        if not local_profile and self.repository_mode == "in-memory":
            raise RuntimeConfigurationError(
                "in-memory archive repository requires local-development or test profile"
            )
        if not local_profile and self.storage_mode == "filesystem":
            raise RuntimeConfigurationError(
                "filesystem archive storage requires local-development or test profile"
            )
        if self.repository_mode == "postgresql" and not self.database_url:
            raise RuntimeConfigurationError("PostgreSQL archive repository requires database URL")
        if self.storage_mode == "s3" and not self.s3_bucket:
            raise RuntimeConfigurationError("S3 archive storage requires bucket")
        if self.s3_server_side_encryption == "aws:kms" and not self.s3_kms_key_id:
            raise RuntimeConfigurationError("S3 KMS encryption requires key ID")
        self._validate_lifecycle_decision_keys(local_profile=local_profile)
        return self

    def _validate_lifecycle_decision_keys(self, *, local_profile: bool) -> None:
        """Signing and verification key material, checked at startup.

        Separated from the composite runtime validator because these are the
        rules with real branching, and because a configuration error here is
        the difference between decisions that stay verifiable and evidence that
        silently cannot be checked.
        """
        encoded_private_key = self.idea_lifecycle_decision_private_key_base64.get_secret_value()
        if encoded_private_key:
            try:
                private_key = b64decode(encoded_private_key, validate=True)
            except (Base64DecodeError, ValueError) as exc:
                raise RuntimeConfigurationError(
                    "lifecycle decision private key must be valid base64"
                ) from exc
            if len(private_key) != 32:
                raise RuntimeConfigurationError(
                    "lifecycle decision Ed25519 private key must contain 32 bytes"
                )
        if not local_profile and (
            not encoded_private_key
            or self.idea_lifecycle_decision_signing_key_id.startswith("ephemeral-local")
        ):
            raise RuntimeConfigurationError(
                "production lifecycle decisions require managed signing key material"
            )
        if not local_profile and self.idea_lifecycle_decision_signing_key_not_before_utc is None:
            raise RuntimeConfigurationError(
                "production lifecycle decisions require a provisioned signing key start instant"
            )
        for retained in self.retained_verification_keys():
            if retained.not_after_utc <= retained.not_before_utc:
                raise RuntimeConfigurationError(
                    "a retained lifecycle verification key window must end after it begins"
                )
        retained_ids = [key.key_id for key in self.retained_verification_keys()]
        duplicates = sorted({i for i in retained_ids if retained_ids.count(i) > 1})
        if duplicates:
            raise RuntimeConfigurationError(
                "retained lifecycle verification key IDs must be unique: " + ", ".join(duplicates)
            )
        if self.idea_lifecycle_decision_signing_key_id in retained_ids:
            # The published bundle would carry one id twice, which lotus-idea's
            # trust bundle rejects outright and which this service's own
            # verifier cannot resolve. Refused at startup, where an operator can
            # still see which list the duplicate came from.
            raise RuntimeConfigurationError(
                "the active signing key ID must not also appear in the retained "
                f"verification keys: {self.idea_lifecycle_decision_signing_key_id}"
            )
        revoked = self.revoked_key_ids()
        published = {key.key_id for key in self.retained_verification_keys()} | {
            self.idea_lifecycle_decision_signing_key_id
        }
        unknown = sorted(revoked - published)
        if unknown:
            # A revoked ID matching no published key is silently inert: it
            # neither withholds a signature nor marks anything in the bundle,
            # so a typo in the one control that withdraws trust would read as
            # applied. Refusing to start is the only way that surfaces.
            raise RuntimeConfigurationError(
                f"revoked lifecycle key IDs match no published key: {', '.join(unknown)}"
            )

    def revoked_key_ids(self) -> frozenset[str]:
        """Key IDs whose signatures are withdrawn.

        Parsed on demand for the same reason as the retained list: a malformed
        value must fail startup validation rather than read as an empty set,
        and an empty revocation set is exactly what a healthy service looks
        like -- so the failure would be invisible in the one direction that
        matters.
        """
        raw = self.idea_lifecycle_decision_revoked_key_ids.strip()
        if not raw:
            return frozenset()
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeConfigurationError(
                "revoked lifecycle verification key IDs must be valid JSON"
            ) from exc
        if not isinstance(entries, list) or not all(
            isinstance(entry, str) and entry.strip() for entry in entries
        ):
            raise RuntimeConfigurationError(
                "revoked lifecycle verification key IDs must be a JSON list of non-empty strings"
            )
        return frozenset(entry.strip() for entry in entries)

    def retained_verification_keys(self) -> tuple[RetainedVerificationKey, ...]:
        """Keys retained so decisions they signed stay verifiable.

        Parsed on demand rather than stored, so a malformed value surfaces as a
        configuration error at startup validation instead of an attribute that
        silently reads as empty -- an empty retained set looks exactly like a
        service that has never rotated.
        """
        raw = self.idea_lifecycle_decision_retained_verification_keys.strip()
        if not raw:
            return ()
        try:
            entries = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeConfigurationError(
                "retained lifecycle verification keys must be valid JSON"
            ) from exc
        if not isinstance(entries, list):
            raise RuntimeConfigurationError(
                "retained lifecycle verification keys must be a JSON list"
            )
        try:
            return tuple(RetainedVerificationKey(**entry) for entry in entries)
        except (TypeError, ValueError) as exc:
            raise RuntimeConfigurationError(
                "a retained lifecycle verification key entry is malformed"
            ) from exc

    @property
    def max_encoded_document_chars(self) -> int:
        return ((self.max_decoded_document_bytes + 2) // 3) * 4
