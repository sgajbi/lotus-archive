from pathlib import Path

import pytest

from app.archive.exceptions import RuntimeConfigurationError
from app.archive.runtime import build_archive_service, runtime_posture
from app.archive.settings import ArchiveRuntimeSettings


def test_runtime_build_rejects_unavailable_postgresql_adapter(tmp_path: Path) -> None:
    settings = ArchiveRuntimeSettings(
        runtime_profile="local-development",
        repository_mode="postgresql",
        database_url="postgresql://archive/test",
        storage_mode="filesystem",
        storage_root=tmp_path / "objects",
    )

    with pytest.raises(RuntimeConfigurationError, match="PostgreSQL archive repository adapter"):
        build_archive_service(settings)


def test_runtime_build_rejects_unavailable_s3_adapter() -> None:
    settings = ArchiveRuntimeSettings(
        runtime_profile="local-development",
        repository_mode="in-memory",
        storage_mode="s3",
    )

    with pytest.raises(RuntimeConfigurationError, match="S3 archive storage adapter"):
        build_archive_service(settings)


def test_runtime_settings_rejects_production_filesystem_storage() -> None:
    with pytest.raises(RuntimeConfigurationError, match="filesystem archive storage"):
        ArchiveRuntimeSettings(
            runtime_profile="production",
            repository_mode="postgresql",
            database_url="postgresql://archive/prod",
            storage_mode="filesystem",
        )


def test_runtime_settings_rejects_postgresql_without_database_url() -> None:
    with pytest.raises(RuntimeConfigurationError, match="PostgreSQL archive repository"):
        ArchiveRuntimeSettings(
            runtime_profile="local-development",
            repository_mode="postgresql",
            storage_mode="filesystem",
        )


def test_runtime_settings_reports_encoded_size_limit() -> None:
    settings = ArchiveRuntimeSettings(max_decoded_document_bytes=5)

    assert settings.max_encoded_document_chars == 8


def test_runtime_posture_reports_unavailable_non_durable_production() -> None:
    settings = ArchiveRuntimeSettings.model_construct(
        runtime_profile="production",
        repository_mode="postgresql",
        storage_mode="filesystem",
        storage_namespace="prod",
        database_url="postgresql://archive/prod",
        max_decoded_document_bytes=1024,
    )

    posture = runtime_posture(settings)

    assert posture.state == "unavailable"
    assert posture.reason == "durable_archive_runtime_missing"
