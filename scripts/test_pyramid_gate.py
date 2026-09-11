"""Hold the shape of the *product's* test suite (archive#144).

The pyramid is a claim about how product behaviour is covered: mostly fast unit
tests, a meaningful band of integration tests, a thin layer of end-to-end tests.
Tests that assert about the repository itself -- its CI contracts, workflows,
gates, documentation posture or migration schema -- are not product tests.
Counting them distorts the shape and makes the gate hostile to the coverage it
should encourage: every governance test added pushes the unit bucket up and
squeezes the others down, so a repository can be blocked from asserting its own
CI contracts. `lotus-risk#220` is where that was first paid for.

Adapted from `lotus-risk/scripts/test_pyramid_gate.py` rather than copied
blindly. Two differences, both measured here:

**The marker was applied to almost the opposite of what it meant.** Archive
carried `pytest.mark.governance` on three modules. One of them tested signing
and verification -- product behaviour, hidden from the pyramid it belonged in --
while thirteen modules that touch no product code at all went unmarked and were
counted as product coverage. Corrected, the shape changed from an apparently
unit-heavy 84.1% to 80.3%, comfortably inside the band. The suite was never
misshapen; its classification was.

**The e2e bucket is gated at a measured floor.** Its named product journeys are
archive/read-back, hold/refuse/release/purge, durable restart/interrupted-purge
completion, and lifecycle-decision verification from the published key bundle.
Together with health and metadata smoke proof, those journeys measured 1.61%
when the floor was established. The 1.5% floor protects that thin outer layer
without making a ratio the reason to add tests.
"""

from __future__ import annotations

import math
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Tests that assert about the repository rather than the product. Deselected from every bucket.
NON_PRODUCT_MARKER_EXPRESSION = "not governance"

# Decimal places used when reporting a ratio. Displayed values are rounded *away* from the bound
# they failed, so a failure message can never print a number that satisfies its own bound.
_DISPLAY_PRECISION = 4


@dataclass(frozen=True)
class BucketPolicy:
    name: str
    path: str
    min_ratio: float
    max_ratio: float


BUCKET_POLICIES = (
    BucketPolicy(name="unit", path="tests/unit", min_ratio=0.70, max_ratio=0.85),
    BucketPolicy(name="integration", path="tests/integration", min_ratio=0.15, max_ratio=0.25),
    BucketPolicy(
        name="e2e",
        path="tests/e2e",
        min_ratio=0.015,
        max_ratio=0.10,
    ),
)

# `--collect-only` reports "collected 712 items / 130 deselected / 582 selected" when a marker
# expression applies and "collected 26 items" when nothing is deselected. Reading the first number
# in the first form yields the pre-deselection total, which would silently defeat the marker.
# Note the absence of `-q` below: the compact form prints "277/396 tests collected (119 deselected)"
# instead, which neither pattern matches, and the gate would fail to collect rather than misread.
_SELECTED = re.compile(r"(\d+)\s+selected")
_COLLECTED = re.compile(r"collected\s+(\d+)\s+items?")


def _collect_count(path: str) -> int:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            path,
            "-m",
            NON_PRODUCT_MARKER_EXPRESSION,
            "--collect-only",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    output = f"{completed.stdout}\n{completed.stderr}"
    match = _SELECTED.search(output) or _COLLECTED.search(output)
    if completed.returncode != 0 or match is None:
        print(f"Failed to collect tests for {path}", file=sys.stderr)
        print(output, file=sys.stderr)
        raise SystemExit(1)
    return int(match.group(1))


def _headroom(policy: BucketPolicy, count: int, total: int) -> tuple[int, int]:
    """Tests that can still be added before this bucket breaches each bound.

    Both bounds move as the suite grows, so neither is a simple subtraction:

        floor   - adding to the OTHER buckets dilutes this one:
                  count / (total + n) >= min   ->   n <= count/min - total
        ceiling - adding to THIS bucket concentrates it:
                  (count + n) / (total + n) <= max  ->  n <= (max*total - count) / (1 - max)

    Published on every run, not only on failure. A ratio near its bound is not
    visible as a number; it is only visible as a distance.
    """

    to_floor = math.floor(count / policy.min_ratio - total)
    to_ceiling = math.floor((policy.max_ratio * total - count) / (1 - policy.max_ratio))
    return max(0, to_floor), max(0, to_ceiling)


def _rounded_away_from(percent: float, *, below_bound: bool) -> str:
    """Render `percent` so it never crosses the bound it failed.

    `f"{2.9954:.2f}"` is `3.00`, which passes the inclusive 3% floor it was reported as failing.
    A message that prints a value satisfying its own bound sends the reader to debug a comparison
    that is correct.
    """

    scale = 10**_DISPLAY_PRECISION
    rounded = math.floor(percent * scale) if below_bound else math.ceil(percent * scale)
    return f"{rounded / scale:.{_DISPLAY_PRECISION}f}"


def _tests_to_add(policy: BucketPolicy, count: int, total: int, *, below_bound: bool) -> int:
    """How many tests must be added to clear the bound, accounting for the moving total.

    A bucket's ratio is measured against a total the bucket is part of, so adding a test changes
    both sides. Solving for tests added *to this bucket* when it is under its floor:

        (count + n) / (total + n) >= min   ->   n >= (min * total - count) / (1 - min)

    and for a ceiling, where the realistic action is adding tests to the *other* buckets rather
    than deleting tests from this one:

        count / (total + n) <= max         ->   n >= count / max - total

    Reporting `min * total` - the naive form - under-shoots, because it treats the total as fixed.
    At 14 of 100 against a 15% floor it advises "at least 15", and 15/101 is 14.85%: still failing.
    """

    if below_bound:
        needed = (policy.min_ratio * total - count) / (1 - policy.min_ratio)
    else:
        needed = count / policy.max_ratio - total
    return max(1, math.ceil(needed))


def _failure_message(policy: BucketPolicy, count: int, total: int, percent: float) -> str:
    below = percent < policy.min_ratio * 100
    bound = policy.min_ratio if below else policy.max_ratio
    side = "below the" if below else "above the"
    limit = "floor" if below else "ceiling"
    needed = _tests_to_add(policy, count, total, below_bound=below)
    where = f"the {policy.name} bucket" if below else "the other buckets"
    plural = "" if needed == 1 else "s"
    return (
        f"test pyramid gate failed for {policy.name}: {count} of {total} product tests is "
        f"{_rounded_away_from(percent, below_bound=below)}%, {side} {bound * 100:g}% {limit}. "
        f"Adding {needed} product test{plural} to {where} clears it - the total moves with the "
        f"bucket, so a count derived from the current total is not enough."
    )


def main() -> int:
    missing = [policy.path for policy in BUCKET_POLICIES if not (ROOT / policy.path).is_dir()]
    if missing:
        # A gate that inspected nothing must fail rather than report a vacuous pass.
        print(f"Configured test bucket paths are missing: {missing}", file=sys.stderr)
        return 1

    counts = {policy.name: _collect_count(policy.path) for policy in BUCKET_POLICIES}
    total = sum(counts.values())
    if total == 0:
        print("No product tests collected.", file=sys.stderr)
        return 1

    failed = False
    for policy in BUCKET_POLICIES:
        count = counts[policy.name]
        percent = count / total * 100
        to_floor, to_ceiling = _headroom(policy, count, total)
        print(
            f"{policy.name}: {count} product tests ({percent:.2f}%) "
            f"target {policy.min_ratio * 100:g}%..{policy.max_ratio * 100:g}% "
            f"| headroom: {to_floor} elsewhere before the floor, "
            f"{to_ceiling} here before the ceiling"
        )
        if not policy.min_ratio <= count / total <= policy.max_ratio:
            failed = True
            print(_failure_message(policy, count, total, percent), file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
