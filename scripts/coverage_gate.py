import sys
from pathlib import Path

import coverage


def main() -> int:
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
