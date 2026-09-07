"""`pytest.mark.governance` is applied by what a module tests (archive#144).

The marker decides whether a module counts as product coverage in
`scripts/test_pyramid_gate.py`. A marker applied by habit rather than by content
moves the pyramid without anybody deciding to, in whichever direction the
mistake happens to run -- and both directions had already happened here:

  A **product** test carrying the mark is hidden from the pyramid it belongs in.
  `test_lifecycle_verification_keys.py` asserts signing-window and revocation
  behaviour and was marked governance, so 18 real product tests were invisible.

  A **governance** test without the mark is counted as product coverage.
  Thirteen modules asserting about workflows, branch protection, CI gate
  liveness, documentation posture and release evidence were counted as product
  tests -- 101 of them.

Together those made archive's suite look unit-heavy at 84.1%, one bad number
away from a ceiling it had no real reason to be near. Corrected, it is 80.3%
with 108 tests of headroom. The suite was never misshapen; its classification
was, and nothing measured the classification.

The discriminator is a **direct** import of `app.`. A module that reaches into
the application package is asserting about the product; one that does not is
asserting about the repository. It is a proxy rather than a definition, so both
escape hatches below are explicit and each use must name its reason.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.governance

UNIT_TESTS = Path(__file__).resolve().parent
PRODUCT_IMPORT = re.compile(r"^\s*(?:from app[\s.]|import app(?:\s|$|\.))", re.MULTILINE)
GOVERNANCE_MARK = "pytest.mark.governance"

#: Modules that touch product code and are still governance tests, with the reason.
#: Kept empty deliberately: an entry here is a module asserting about the
#: repository *through* the application package, which is usually a sign the
#: assertion belongs somewhere else.
PRODUCT_IMPORTING_GOVERNANCE: dict[str, str] = {}

#: Modules that touch no product code and are still product tests, with the reason.
#: `test_migration_schema_coverage.py` is the near-miss: it imports the gate
#: script, which imports the models, so it never names `app.` itself -- and it
#: genuinely is a governance test, so it is marked and needs no entry here.
NON_PRODUCT_PRODUCT_TESTS: dict[str, str] = {}


def _modules() -> list[Path]:
    return sorted(path for path in UNIT_TESTS.glob("test_*.py") if path.name != Path(__file__).name)


def _reads(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("module", _modules(), ids=lambda path: path.name)
def test_a_module_touching_product_code_is_not_marked_governance(module: Path) -> None:
    """The direction that hides real coverage.

    A product test carrying the mark is deselected from the pyramid, so the
    product looks less covered than it is and the unit bucket looks smaller. It
    fails silently in the safe-looking direction, which is why it survived.
    """
    body = _reads(module)
    if not PRODUCT_IMPORT.search(body):
        pytest.skip("asserts about the repository; covered by the other direction")

    if module.name in PRODUCT_IMPORTING_GOVERNANCE:
        assert PRODUCT_IMPORTING_GOVERNANCE[module.name].strip(), "an exemption needs its reason"
        return

    assert GOVERNANCE_MARK not in body, (
        f"{module.name} imports app code, so it asserts about the product and must not be "
        "deselected from the pyramid. If it genuinely asserts about the repository through the "
        "application package, add it to PRODUCT_IMPORTING_GOVERNANCE with the reason"
    )


@pytest.mark.parametrize("module", _modules(), ids=lambda path: path.name)
def test_a_module_touching_no_product_code_is_marked_governance(module: Path) -> None:
    """The direction that inflates the unit bucket.

    101 tests across thirteen modules were counted as product coverage while
    asserting about workflows, gates and documentation. This is the direction
    `lotus-risk#220` was filed for: governance tests crowding the pyramid until
    it turns hostile to the repository asserting its own contracts.
    """
    body = _reads(module)
    if PRODUCT_IMPORT.search(body):
        pytest.skip("asserts about the product; covered by the other direction")

    if module.name in NON_PRODUCT_PRODUCT_TESTS:
        assert NON_PRODUCT_PRODUCT_TESTS[module.name].strip(), "an exemption needs its reason"
        return

    assert GOVERNANCE_MARK in body, (
        f"{module.name} imports no app code, so it asserts about the repository and must carry "
        "pytest.mark.governance or it inflates the unit bucket. If it does test product "
        "behaviour without naming the package, add it to NON_PRODUCT_PRODUCT_TESTS with the reason"
    )


def test_the_marker_is_registered() -> None:
    """An unregistered mark warns on every run and selects nothing.

    Registering it alone would have been the worse outcome -- a label that looks
    like a lane and is not one -- which is why it lands together with the two
    consumers that read it: this classification invariant and the pyramid gate.
    """
    pyproject = (UNIT_TESTS.parents[1] / "pyproject.toml").read_text(encoding="utf-8")

    assert "governance:" in pyproject, "the marker must be registered in [tool.pytest.ini_options]"


def test_the_marker_actually_deselects() -> None:
    """The mark changes what a lane collects, rather than merely existing.

    A registered marker that no expression selects on is indistinguishable from
    a comment. This asserts the two counts differ, so the deselection is a
    measured fact rather than a configured intention.
    """
    import subprocess
    import sys

    def collected(*extra: str) -> int:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(UNIT_TESTS), "--collect-only", *extra],
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        selected = re.search(r"(\d+)\s+selected", output)
        collected_items = re.search(r"collected\s+(\d+)\s+items?", output)
        match = selected or collected_items
        assert match, f"could not read a count from:\n{output[-2000:]}"
        return int(match.group(1))

    everything = collected()
    product_only = collected("-m", "not governance")

    assert product_only < everything, (
        "deselecting governance tests must reduce the unit lane; if these are equal the marker "
        "is applied to nothing and the pyramid gate is measuring the whole suite"
    )
