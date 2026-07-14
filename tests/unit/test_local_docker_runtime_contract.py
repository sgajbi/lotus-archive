from pathlib import Path
import re

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_local_compose_does_not_require_untracked_env_file() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    env_file = compose["services"]["lotus-archive"]["env_file"]

    assert env_file == [{"path": ".env", "required": False}]


def test_dockerfile_builds_production_runtime_without_dev_dependencies() -> None:
    dockerfile = _read("Dockerfile")

    assert "AS wheel-builder" in dockerfile
    assert "AS runtime" in dockerfile
    assert "pip wheel --no-cache-dir --wheel-dir /wheels ." in dockerfile
    assert "pip install --no-cache-dir /wheels/*.whl" in dockerfile
    assert ".[dev]" not in dockerfile
    assert "pip install --no-cache-dir -e" not in dockerfile
    assert "USER lotus" in dockerfile


def test_dockerfile_exposes_source_safe_oci_and_runtime_metadata() -> None:
    dockerfile = _read("Dockerfile")

    for label in [
        "org.opencontainers.image.version",
        "org.opencontainers.image.revision",
        "org.opencontainers.image.source",
        "org.opencontainers.image.ref.name",
        "org.opencontainers.image.created",
        "io.lotus.pipeline.run-id",
        "io.lotus.image.ref",
        "io.lotus.image.digest",
    ]:
        assert label in dockerfile

    for env_name in [
        "LOTUS_ARCHIVE_COMMIT_SHA",
        "LOTUS_ARCHIVE_REPOSITORY_URL",
        "LOTUS_ARCHIVE_BUILD_REF",
        "LOTUS_ARCHIVE_BUILD_TIMESTAMP_UTC",
        "LOTUS_ARCHIVE_CI_RUN_ID",
        "LOTUS_ARCHIVE_IMAGE_REF",
        "LOTUS_ARCHIVE_IMAGE_DIGEST",
    ]:
        assert env_name in dockerfile


def test_dockerfile_does_not_define_secret_like_build_arguments_or_labels() -> None:
    dockerfile = _read("Dockerfile")
    secret_like = re.compile(r"(?i)(secret|token|password|credential|private[_-]?key)")

    for line in dockerfile.splitlines():
        if line.startswith(("ARG ", "ENV ", "LABEL ")):
            assert secret_like.search(line) is None, line


def test_makefile_tags_local_and_release_images_with_build_metadata() -> None:
    makefile = _read("Makefile")

    assert "docker-build:" in makefile
    assert "-t $(LOTUS_ARCHIVE_IMAGE_REF)" in makefile
    assert "backend-service:ci-test" not in makefile
    assert "docker-release-build:" in makefile
    assert "--metadata-file $(RELEASE_METADATA_FILE)" in makefile
    assert "--provenance=true" in makefile
    assert "--sbom=true" in makefile
    assert "--push -t $(RELEASE_IMAGE_NAME):$(RELEASE_IMAGE_TAG)" in makefile
    assert "release-evidence:" in makefile
    assert "scripts/generate_release_evidence.py" in makefile


def test_release_workflows_record_image_identity_evidence() -> None:
    main_workflow = _read(".github/workflows/main-releasability.yml")
    pr_workflow = _read(".github/workflows/pr-merge-gate.yml")

    assert "LOTUS_ARCHIVE_IMAGE_REF: lotus-archive:${{ github.sha }}" in pr_workflow
    assert "LOTUS_ARCHIVE_COMMIT_SHA: ${{ github.sha }}" in pr_workflow
    assert "docker image inspect" in pr_workflow
    assert "image-labels.json" in pr_workflow

    workflow = yaml.safe_load(main_workflow)
    docker_job = workflow["jobs"]["docker-build"]
    steps = {step["name"]: step for step in docker_job["steps"] if "name" in step}

    assert docker_job["permissions"] == {
        "attestations": "write",
        "artifact-metadata": "write",
        "contents": "read",
        "id-token": "write",
        "packages": "write",
    }
    assert steps["Build and push release image"]["run"] == "make docker-release-build"
    assert steps["Generate release metadata manifest"]["run"] == "make release-evidence"
    assert "sigstore/cosign-installer@v4.1.0" in main_workflow
    assert (
        steps["Scan release image for vulnerabilities"]["uses"]
        == "aquasecurity/trivy-action@v0.36.0"
    )
    assert steps["Generate GitHub provenance attestation"]["uses"] == "actions/attest@v4"
    assert "cosign sign --yes" in steps["Sign release image digest"]["run"]
    assert "cosign verify" in steps["Verify release image signature"]["run"]
    assert "gh attestation verify" in steps["Verify GitHub provenance attestation"]["run"]
    assert steps["Verify GitHub provenance attestation"]["env"] == {
        "GH_TOKEN": "${{ github.token }}"
    }
    assert "--signer-workflow" not in steps["Verify GitHub provenance attestation"]["run"]
    assert "--cert-identity" in steps["Verify GitHub provenance attestation"]["run"]
    assert (
        '"https://github.com/${GITHUB_REPOSITORY}/.github/workflows/main-releasability.yml@refs/heads/main"'
        in steps["Verify GitHub provenance attestation"]["run"]
    )
    assert (
        '--cert-oidc-issuer "https://token.actions.githubusercontent.com"'
        in steps["Verify GitHub provenance attestation"]["run"]
    )
    assert (
        '"${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/.github/workflows/main-releasability.yml"'
        not in steps["Verify GitHub provenance attestation"]["run"]
    )
    assert '--source-ref "refs/heads/main"' in steps["Verify GitHub provenance attestation"]["run"]
    assert '--source-digest "${GITHUB_SHA}"' in steps["Verify GitHub provenance attestation"]["run"]
    assert "image-build-metadata.json" in main_workflow
    assert "release-evidence.json" in main_workflow
