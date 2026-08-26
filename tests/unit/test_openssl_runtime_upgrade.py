"""Contract for the temporary OpenSSL base-image remediation owned by issue #85."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "Dockerfile"


def _upgrade_instruction() -> str:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    match = re.search(
        r"RUN apt-get update \\\n(?P<body>.*?rm -rf /var/lib/apt/lists/\*)",
        dockerfile,
        flags=re.DOTALL,
    )
    assert match is not None, "The targeted OpenSSL remediation block is missing"
    return match.group(0)


def test_openssl_remediation_is_targeted_and_version_guarded() -> None:
    instruction = _upgrade_instruction()

    assert "--only-upgrade" in instruction
    assert "openssl libssl3t64 openssl-provider-legacy" in instruction
    assert 'dpkg --compare-versions "$(dpkg-query' in instruction
    assert 'openssl)" ge \\\n        "3.5.7-1~deb13u2"' in instruction
    assert re.search(r"apt-get\s+upgrade", instruction) is None
    assert re.search(r"(?:apt|apt-get)\s+dist-upgrade", instruction) is None


def test_openssl_remediation_cleans_package_metadata_and_records_removal_condition() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    instruction = _upgrade_instruction()

    assert instruction.rstrip().endswith("rm -rf /var/lib/apt/lists/*")
    normalized_comments = " ".join(
        line.removeprefix("#").strip()
        for line in dockerfile.splitlines()
        if line.lstrip().startswith("#")
    )
    assert "Remove this block once the base image carries 3.5.7 or later" in normalized_comments
    assert "CVE-2026-14456" in dockerfile


def test_openssl_remediation_does_not_weaken_vulnerability_scanning() -> None:
    repository_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "Dockerfile",
            ROOT / ".github" / "workflows" / "main-releasability.yml",
        )
    )

    assert "trivyignores" not in repository_text
    assert "severity: CRITICAL,HIGH" in repository_text
    assert 'exit-code: "1"' in repository_text
