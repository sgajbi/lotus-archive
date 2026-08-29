from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = ROOT / "Makefile"
VALIDATION_WORKFLOWS = (
    ROOT / ".github/workflows/feature-lane.yml",
    ROOT / ".github/workflows/pr-merge-gate.yml",
    ROOT / ".github/workflows/main-releasability.yml",
)


def _target_dependencies(makefile: str, target: str) -> set[str]:
    match = re.search(rf"^{re.escape(target)}:[ \t]+([^\r\n]+)$", makefile, re.MULTILINE)
    assert match is not None, f"Make target {target!r} is missing or has no dependencies."
    return set(match.group(1).split())


def test_every_blocking_make_gate_is_live_in_each_validation_workflow() -> None:
    """A locally advertised gate is not a control until every blocking lane executes it."""

    makefile = MAKEFILE.read_text(encoding="utf-8")
    blocking_dependencies = _target_dependencies(makefile, "check") | _target_dependencies(
        makefile, "ci"
    )
    blocking_gates = {target for target in blocking_dependencies if target.endswith("-gate")}
    assert blocking_gates, "The blocking Make lanes advertise no *-gate targets."

    for workflow in VALIDATION_WORKFLOWS:
        workflow_text = workflow.read_text(encoding="utf-8")
        invoked_targets = set(re.findall(r"\bmake[ \t]+([A-Za-z0-9_-]+)", workflow_text))
        missing = sorted(blocking_gates - invoked_targets)
        assert missing == [], (
            f"{workflow.name} does not execute blocking Make gates {missing}. "
            "A gate that only appears in check/ci remains invisible because workflows invoke "
            "repository targets individually."
        )
