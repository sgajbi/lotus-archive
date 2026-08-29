from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64DecodeError
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.archive.exceptions import RuntimeConfigurationError

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

    @model_validator(mode="after")
    def validate_runtime_posture(self) -> ArchiveRuntimeSettings:
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
        return self

    @property
    def max_encoded_document_chars(self) -> int:
        return ((self.max_decoded_document_bytes + 2) // 3) * 4
