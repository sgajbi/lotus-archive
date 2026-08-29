from base64 import b64encode
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import SecretStr
from starlette.requests import Request

from app.archive.api import idea_lifecycle_decision_service
from app.archive.exceptions import RuntimeConfigurationError
from app.archive.postgres_repository import (
    PostgresAccessAuditRepository,
    PostgresArchiveDocumentRepository,
)
from app.archive.runtime import build_archive_service, runtime_posture
from app.archive.s3_storage import S3ObjectStorage
from app.archive.settings import ArchiveRuntimeSettings


def test_runtime_builds_postgresql_metadata_and_audit_adapters(tmp_path: Path) -> None:
    settings = ArchiveRuntimeSettings(
        runtime_profile="local-development",
        repository_mode="postgresql",
        database_url="postgresql://archive/test",
        storage_mode="filesystem",
        storage_root=tmp_path / "objects",
    )

    service = build_archive_service(settings)

    assert isinstance(service.repository, PostgresArchiveDocumentRepository)
    assert isinstance(service.audit_repository, PostgresAccessAuditRepository)


def test_runtime_builds_s3_storage_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    settings = ArchiveRuntimeSettings(
        runtime_profile="local-development",
        repository_mode="in-memory",
        storage_mode="s3",
        s3_bucket="lotus-archive-test",
    )

    service = build_archive_service(settings)

    assert isinstance(service.storage, S3ObjectStorage)


def test_runtime_builds_complete_production_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    settings = ArchiveRuntimeSettings(
        runtime_profile="production",
        repository_mode="postgresql",
        database_url="postgresql://archive/prod",
        storage_mode="s3",
        s3_bucket="lotus-archive-production",
        idea_lifecycle_decision_private_key_base64=SecretStr(b64encode(b"x" * 32).decode("ascii")),
        idea_lifecycle_decision_signing_key_id="managed-archive-v1",
    )

    service = build_archive_service(settings)
    posture = runtime_posture(settings)

    assert isinstance(service.repository, PostgresArchiveDocumentRepository)
    assert isinstance(service.audit_repository, PostgresAccessAuditRepository)
    assert isinstance(service.storage, S3ObjectStorage)
    assert posture.state == "ready"
    assert posture.durable_metadata is True
    assert posture.durable_audit is True
    assert posture.durable_storage is True


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


def test_runtime_settings_rejects_s3_without_bucket() -> None:
    with pytest.raises(RuntimeConfigurationError, match="S3 archive storage requires bucket"):
        ArchiveRuntimeSettings(storage_mode="s3")


def test_runtime_settings_rejects_kms_encryption_without_key() -> None:
    with pytest.raises(RuntimeConfigurationError, match="KMS encryption requires key ID"):
        ArchiveRuntimeSettings(
            storage_mode="s3",
            s3_bucket="lotus-archive-test",
            s3_server_side_encryption="aws:kms",
        )


def test_runtime_settings_rejects_production_without_managed_decision_key() -> None:
    with pytest.raises(RuntimeConfigurationError, match="managed signing key material"):
        ArchiveRuntimeSettings(
            runtime_profile="production",
            repository_mode="postgresql",
            database_url="postgresql://archive/prod",
            storage_mode="s3",
            s3_bucket="lotus-archive-production",
        )


def test_runtime_settings_reports_encoded_size_limit() -> None:
    settings = ArchiveRuntimeSettings(max_decoded_document_bytes=5)

    assert settings.max_encoded_document_chars == 8


@pytest.mark.parametrize("private_key", ["not-base64", "YQ=="])
def test_runtime_settings_rejects_invalid_lifecycle_signing_key(private_key: str) -> None:
    with pytest.raises(RuntimeConfigurationError, match="lifecycle decision"):
        ArchiveRuntimeSettings(idea_lifecycle_decision_private_key_base64=SecretStr(private_key))


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


def test_lifecycle_decision_dependency_builds_and_caches_local_service(
    tmp_path: Path,
) -> None:
    state = SimpleNamespace(
        archive_runtime_settings=ArchiveRuntimeSettings(
            storage_root=tmp_path / "objects",
            idea_lifecycle_decision_ledger_path=tmp_path / "decisions.sqlite3",
        )
    )
    request = cast(
        Request,
        SimpleNamespace(app=SimpleNamespace(state=state)),
    )

    first = idea_lifecycle_decision_service(request)
    second = idea_lifecycle_decision_service(request)

    assert second is first


def test_runtime_threads_operational_bounds_into_both_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The composed service must carry the configured timeouts, not module defaults."""
    from base64 import b64encode

    from pydantic import SecretStr

    import app.archive.runtime as runtime_module
    from app.archive.settings import ArchiveRuntimeSettings

    captured: dict[str, dict[str, object]] = {}

    class _Recorder:
        def __init__(self, name: str):
            self._name = name

        def __call__(self, *args: object, **kwargs: object) -> object:
            captured[self._name] = {"args": args, **kwargs}
            return object()

    monkeypatch.setattr(
        runtime_module, "PostgresArchiveDocumentRepository", _Recorder("repository")
    )
    monkeypatch.setattr(runtime_module, "PostgresAccessAuditRepository", _Recorder("audit"))
    monkeypatch.setattr(runtime_module, "S3ObjectStorage", _Recorder("storage"))
    monkeypatch.setattr(runtime_module, "ArchiveWriter", _Recorder("writer"))
    monkeypatch.setattr(runtime_module, "ArchiveDocumentService", _Recorder("service"))

    settings = ArchiveRuntimeSettings(
        runtime_profile="production",
        repository_mode="postgresql",
        storage_mode="s3",
        database_url="postgresql://u:p@h/db",
        database_connect_timeout_seconds=9,
        database_statement_timeout_ms=4500,
        s3_bucket="lotus-archive",
        s3_connect_timeout_seconds=2.0,
        s3_read_timeout_seconds=8.0,
        s3_max_attempts=5,
        idea_lifecycle_decision_private_key_base64=SecretStr(b64encode(b"0" * 32).decode()),
        idea_lifecycle_decision_signing_key_id="managed-v1",
    )
    runtime_module.build_archive_service(settings)

    assert captured["repository"]["connect_timeout_seconds"] == 9
    assert captured["repository"]["statement_timeout_ms"] == 4500
    assert captured["audit"]["connect_timeout_seconds"] == 9
    assert captured["audit"]["statement_timeout_ms"] == 4500
    assert captured["storage"]["connect_timeout_seconds"] == 2.0
    assert captured["storage"]["read_timeout_seconds"] == 8.0
    assert captured["storage"]["max_attempts"] == 5
