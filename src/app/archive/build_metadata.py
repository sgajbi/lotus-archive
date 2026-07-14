from __future__ import annotations

import os
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field


DEFAULT_REPOSITORY_URL = "https://github.com/sgajbi/lotus-archive"
DEFAULT_SERVICE_NAME = "lotus-archive"
DEFAULT_SERVICE_VERSION = "0.1.0"
LOCAL_VALUE = "local"
UNPUBLISHED_IMAGE_DIGEST = "not-published"


class BuildMetadata(BaseModel):
    service: str = Field(description="Lotus service name for the running process.")
    version: str = Field(description="Service package or release version.")
    commit_sha: str = Field(description="Git commit SHA used to build the image or process.")
    repository_url: str = Field(description="Source repository URL without credentials.")
    git_ref: str = Field(description="Git branch, tag, or ref used for the build.")
    build_timestamp_utc: str = Field(description="UTC timestamp supplied by the build pipeline.")
    ci_run_id: str = Field(description="CI pipeline run identifier that produced the build.")
    image_ref: str = Field(description="Image reference used for the local or CI build.")
    image_digest: str = Field(description="Immutable image digest when published by CI.")
    image_digest_posture: Literal["immutable_digest", "not_published"] = Field(
        description="Whether the runtime is bound to a published immutable image digest."
    )


def _env(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    return value or default


def _source_safe_repository_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.username or parsed.password or "@" in parsed.netloc:
        return "invalid-repository-url-redacted"
    return value


def _image_digest_posture(image_digest: str) -> Literal["immutable_digest", "not_published"]:
    if image_digest.startswith("sha256:") and len(image_digest) > len("sha256:"):
        return "immutable_digest"
    return "not_published"


def build_metadata() -> BuildMetadata:
    image_digest = _env("LOTUS_ARCHIVE_IMAGE_DIGEST", UNPUBLISHED_IMAGE_DIGEST)
    return BuildMetadata(
        service=_env("LOTUS_ARCHIVE_SERVICE_NAME", DEFAULT_SERVICE_NAME),
        version=_env("LOTUS_ARCHIVE_VERSION", DEFAULT_SERVICE_VERSION),
        commit_sha=_env("LOTUS_ARCHIVE_COMMIT_SHA", LOCAL_VALUE),
        repository_url=_source_safe_repository_url(
            _env("LOTUS_ARCHIVE_REPOSITORY_URL", DEFAULT_REPOSITORY_URL)
        ),
        git_ref=_env("LOTUS_ARCHIVE_BUILD_REF", LOCAL_VALUE),
        build_timestamp_utc=_env("LOTUS_ARCHIVE_BUILD_TIMESTAMP_UTC", LOCAL_VALUE),
        ci_run_id=_env("LOTUS_ARCHIVE_CI_RUN_ID", LOCAL_VALUE),
        image_ref=_env("LOTUS_ARCHIVE_IMAGE_REF", "lotus-archive:local"),
        image_digest=image_digest,
        image_digest_posture=_image_digest_posture(image_digest),
    )
