import json
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.generate_release_evidence import (
    build_release_evidence,
    image_digest_from_metadata,
    main,
)


def _evidence(**overrides: object) -> dict[str, Any]:
    values: dict[str, Any] = {
        "repository": "sgajbi/lotus-archive",
        "commit_sha": "a" * 40,
        "git_ref": "refs/heads/main",
        "workflow": "Main Releasability Gate",
        "run_id": "29290000000",
        "image_name": "ghcr.io/sgajbi/lotus-archive",
        "image_tag": "a" * 40,
        "build_timestamp_utc": "2026-07-14T00:00:00Z",
        "repository_url": "https://github.com/sgajbi/lotus-archive",
        "buildx_metadata": {"containerimage.digest": "sha256:" + "b" * 64},
    }
    values.update(overrides)
    return build_release_evidence(**values)


def test_image_digest_is_read_from_buildx_metadata() -> None:
    assert image_digest_from_metadata({"containerimage.digest": "sha256:" + "a" * 64}) == (
        "sha256:" + "a" * 64
    )


def test_release_evidence_binds_image_digest_to_runtime_metadata() -> None:
    evidence = _evidence()

    image = cast(dict[str, Any], evidence["image"])
    runtime_environment = cast(dict[str, str], image["runtime_environment"])
    oci_labels = cast(dict[str, str], image["oci_labels"])
    sbom = cast(dict[str, bool], evidence["sbom"])
    provenance = cast(dict[str, bool], evidence["provenance"])

    assert image["digest"] == "sha256:" + "b" * 64
    assert image["digest_ref"] == "ghcr.io/sgajbi/lotus-archive@sha256:" + "b" * 64
    assert runtime_environment["LOTUS_ARCHIVE_IMAGE_DIGEST"] == "sha256:" + "b" * 64
    assert runtime_environment["LOTUS_ARCHIVE_IMAGE_REF"] == (
        "ghcr.io/sgajbi/lotus-archive:" + "a" * 40
    )
    assert oci_labels["org.opencontainers.image.revision"] == "a" * 40
    assert oci_labels["io.lotus.image.digest"] == "sha256:" + "b" * 64
    assert sbom["image_bound"] is True
    assert provenance["image_bound"] is True


def test_release_evidence_rejects_credentialed_repository_url() -> None:
    with pytest.raises(ValueError, match="repository_url"):
        _evidence(repository_url="https://token@example.com/sgajbi/lotus-archive")


def test_release_evidence_rejects_secret_like_metadata_values() -> None:
    with pytest.raises(ValueError, match="secret-like"):
        _evidence(git_ref="refs/heads/add-secret-token")


def test_release_evidence_cli_creates_output_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_path = tmp_path / "image-build-metadata.json"
    metadata_path.write_text(
        json.dumps({"containerimage.digest": "sha256:" + "c" * 64}),
        encoding="utf-8",
    )
    output_path = tmp_path / "nested" / "release-evidence.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_release_evidence.py",
            "--buildx-metadata",
            str(metadata_path),
            "--output",
            str(output_path),
        ],
    )

    assert main() == 0
    assert output_path.exists()
    evidence = json.loads(output_path.read_text(encoding="utf-8"))
    assert evidence["image"]["name"] == "ghcr.io/sgajbi/lotus-archive"
