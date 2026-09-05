import sys
from pathlib import Path

import coverage


def main() -> int:
    """The ONE coverage comparison, local and CI alike.

    The precise combined total is compared against 99.00 - never a rounded
    report figure, whose half-point acceptance band once let CI pass a main
    the documented local gate failed (issue #120). CI passes its downloaded
    artifact directory as argv[1]; local runs combine the suite files in
    the working directory.
    """

    if len(sys.argv) > 1:
        files = sorted(str(path) for path in Path(sys.argv[1]).glob(".coverage.*"))
        if not files:
            print(f"No coverage files found in {sys.argv[1]}")
            return 1
    else:
        files = [".coverage.unit", ".coverage.integration", ".coverage.e2e"]
        missing = [f for f in files if not Path(f).exists()]
        if missing:
            print(f"Missing coverage files: {missing}")
            return 1
    cov = coverage.Coverage()
    cov.combine(files)
    cov.save()
    total = cov.report()
    if total < 99.0:
        print(f"Coverage gate failed: {total:.2f} < 99.00")
        return 1
    print(f"Coverage gate passed: {total:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
