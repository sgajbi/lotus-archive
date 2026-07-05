from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Literal

from pydantic import Field, model_validator
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
        return self

    @property
    def max_encoded_document_chars(self) -> int:
        return ((self.max_decoded_document_bytes + 2) // 3) * 4
