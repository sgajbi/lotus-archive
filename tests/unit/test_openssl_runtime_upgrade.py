"""Contract for the temporary OpenSSL base-image remediation owned by issue #85."""

from pathlib import Path
import re


import pytest


pytestmark = pytest.mark.governance

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


#: Every base-image package the remediation block upgrades, with the minimum
#: version its dpkg assertion requires. The Dockerfile block and this table
#: must move together: a package listed here but not asserted in the block (or
#: the reverse) is drift in the temporary remediation this test exists to keep
#: honest and removable.
REMEDIATED_PACKAGE_FLOORS = {
    "openssl": "3.5.7-1~deb13u2",
    "gzip": "1.13-1+deb13u1",
    "libpcre2-8-0": "10.46-1~deb13u2",
    "libsqlite3-0": "3.46.1-7+deb13u2",
    "perl-base": "5.40.1-6+deb13u1",
}


def test_remediation_is_targeted_and_version_guarded() -> None:
    instruction = _upgrade_instruction()

    assert "--only-upgrade" in instruction
    assert "openssl libssl3t64 openssl-provider-legacy" in instruction
    assert "gzip libpcre2-8-0 libsqlite3-0 perl-base" in instruction
    assert 'dpkg --compare-versions "$(dpkg-query' in instruction
    for package, floor in REMEDIATED_PACKAGE_FLOORS.items():
        assert f'{package})" ge \\\n        "{floor}"' in instruction, (
            f"the remediation block must assert {package} >= {floor}"
        )
    asserted = re.findall(r"--showformat='\$\{Version\}'\s+([a-z0-9.+-]+)\)", instruction)
    assert sorted(asserted) == sorted(REMEDIATED_PACKAGE_FLOORS), (
        "every dpkg version assertion must be listed in REMEDIATED_PACKAGE_FLOORS, and vice versa"
    )
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
