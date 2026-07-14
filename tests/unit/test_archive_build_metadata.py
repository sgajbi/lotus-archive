from app.archive import build_metadata as build_metadata_module
from app.archive.build_metadata import build_metadata


def test_build_metadata_uses_source_safe_local_defaults(monkeypatch) -> None:
    for name in [
        "LOTUS_ARCHIVE_SERVICE_NAME",
        "LOTUS_ARCHIVE_VERSION",
        "LOTUS_ARCHIVE_COMMIT_SHA",
        "LOTUS_ARCHIVE_REPOSITORY_URL",
        "LOTUS_ARCHIVE_BUILD_REF",
        "LOTUS_ARCHIVE_BUILD_TIMESTAMP_UTC",
        "LOTUS_ARCHIVE_CI_RUN_ID",
        "LOTUS_ARCHIVE_IMAGE_REF",
        "LOTUS_ARCHIVE_IMAGE_DIGEST",
    ]:
        monkeypatch.delenv(name, raising=False)

    metadata = build_metadata()

    assert metadata.service == "lotus-archive"
    assert metadata.version == "0.1.0"
    assert metadata.repository_url == "https://github.com/sgajbi/lotus-archive"
    assert metadata.image_digest == "not-published"
    assert metadata.image_digest_posture == "not_published"


def test_build_metadata_reports_immutable_digest_when_deployment_supplies_digest(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOTUS_ARCHIVE_IMAGE_DIGEST", "sha256:" + "a" * 64)

    metadata = build_metadata()

    assert metadata.image_digest == "sha256:" + "a" * 64
    assert metadata.image_digest_posture == "immutable_digest"


def test_build_metadata_redacts_credentialed_repository_url(monkeypatch) -> None:
    monkeypatch.setenv("LOTUS_ARCHIVE_REPOSITORY_URL", "https://token@example.com/sgajbi/archive")

    metadata = build_metadata_module.build_metadata()

    assert metadata.repository_url == "invalid-repository-url-redacted"
