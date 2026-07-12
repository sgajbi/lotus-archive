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
