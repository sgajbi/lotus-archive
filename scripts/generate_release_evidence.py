from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, cast


SCHEMA_VERSION = "lotus-archive-release-evidence.v1"
SECRET_LIKE = re.compile(r"(?i)(secret|token|password|credential|private[_-]?key)")


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    return value or default


def load_buildx_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def image_digest_from_metadata(metadata: dict[str, Any]) -> str:
    digest = metadata.get("containerimage.digest")
    return str(digest) if digest else ""


def validate_source_safe_metadata(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for key, value in values.items():
        if SECRET_LIKE.search(key):
            errors.append(f"release metadata key is secret-like: {key}")
        if SECRET_LIKE.search(value):
            errors.append(f"release metadata value for {key} is secret-like")
    repository_url = values.get("repository_url", "")
    if "@" in repository_url:
        errors.append("repository_url must not contain credentials")
    return errors


def build_release_evidence(
    *,
    repository: str,
    commit_sha: str,
    git_ref: str,
    workflow: str,
    run_id: str,
    image_name: str,
    image_tag: str,
    build_timestamp_utc: str,
    repository_url: str,
    buildx_metadata: dict[str, Any],
) -> dict[str, Any]:
    digest = image_digest_from_metadata(buildx_metadata)
    image_ref = f"{image_name}:{image_tag}"
    image_digest_ref = f"{image_name}@{digest}" if digest else ""
    source_values = {
        "repository": repository,
        "commit_sha": commit_sha,
        "git_ref": git_ref,
        "workflow": workflow,
        "run_id": run_id,
        "image_name": image_name,
        "image_tag": image_tag,
        "build_timestamp_utc": build_timestamp_utc,
        "repository_url": repository_url,
    }
    errors = validate_source_safe_metadata(source_values)
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "repository": repository,
        "commit_sha": commit_sha,
        "ref": git_ref,
        "workflow": workflow,
        "run_id": run_id,
        "dockerfile_path": "Dockerfile",
        "image": {
            "name": image_name,
            "tag": image_tag,
            "ref": image_ref,
            "digest": digest,
            "digest_ref": image_digest_ref,
            "oci_labels": {
                "org.opencontainers.image.version": _env("SERVICE_VERSION", "0.1.0"),
                "org.opencontainers.image.revision": commit_sha,
                "org.opencontainers.image.source": repository_url,
                "org.opencontainers.image.ref.name": git_ref,
                "org.opencontainers.image.created": build_timestamp_utc,
                "io.lotus.pipeline.run-id": run_id,
                "io.lotus.image.ref": image_ref,
                "io.lotus.image.digest": digest,
            },
            "runtime_environment": {
                "LOTUS_ARCHIVE_COMMIT_SHA": commit_sha,
                "LOTUS_ARCHIVE_REPOSITORY_URL": repository_url,
                "LOTUS_ARCHIVE_BUILD_REF": git_ref,
                "LOTUS_ARCHIVE_BUILD_TIMESTAMP_UTC": build_timestamp_utc,
                "LOTUS_ARCHIVE_CI_RUN_ID": run_id,
                "LOTUS_ARCHIVE_IMAGE_REF": image_ref,
                "LOTUS_ARCHIVE_IMAGE_DIGEST": digest,
            },
        },
        "sbom": {
            "generation": "docker-buildx-sbom",
            "image_bound": True,
        },
        "provenance": {
            "generation": "docker-buildx-provenance",
            "image_bound": True,
        },
        "non_proof_boundaries": [
            "Release evidence proves CI image metadata and buildx attestation output only.",
            "Environment promotion remains uncertified until deployment manifests consume digest_ref.",
            "Keyless signature verification remains governed by the CI lane that signs the pushed digest.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate lotus-archive release evidence.")
    parser.add_argument("--buildx-metadata", type=Path, default=Path("image-build-metadata.json"))
    parser.add_argument("--output", type=Path, default=Path("release-evidence.json"))
    args = parser.parse_args()

    build_timestamp = _env("LOTUS_ARCHIVE_BUILD_TIMESTAMP_UTC", datetime.now(UTC).isoformat())
    repository = _env("GITHUB_REPOSITORY", "sgajbi/lotus-archive")
    image_name = _env("RELEASE_IMAGE_NAME", f"ghcr.io/{repository}")
    image_tag = _env("RELEASE_IMAGE_TAG", _env("GITHUB_SHA", "local"))
    try:
        evidence = build_release_evidence(
            repository=repository,
            commit_sha=_env("GITHUB_SHA", "local"),
            git_ref=_env("GITHUB_REF", "local"),
            workflow=_env("GITHUB_WORKFLOW", "local"),
            run_id=_env("GITHUB_RUN_ID", "local"),
            image_name=image_name,
            image_tag=image_tag,
            build_timestamp_utc=build_timestamp,
            repository_url=_env(
                "LOTUS_ARCHIVE_REPOSITORY_URL", "https://github.com/sgajbi/lotus-archive"
            ),
            buildx_metadata=load_buildx_metadata(args.buildx_metadata),
        )
    except ValueError as exc:
        print(f"release evidence error: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
