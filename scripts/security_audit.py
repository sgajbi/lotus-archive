from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "security" / "pip-audit-exceptions.json"
RUNTIME_LOCK = ROOT / "requirements" / "shared-runtime.lock.txt"
CI_LOCK = ROOT / "requirements" / "ci-tooling.lock.txt"

REQUIRED_FIELDS = {
    "advisory_id",
    "affected_package",
    "severity",
    "owner",
    "review_by",
    "rationale",
    "dependency_constraint",
    "removal_condition",
    "compensating_controls",
}


def load_policy(path: Path = POLICY_PATH) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def validate_policy(
    policy: dict[str, Any],
    *,
    today: date | None = None,
    runtime_lock_text: str | None = None,
) -> list[str]:
    errors: list[str] = []
    effective_today = today or date.today()
    lock_text = (
        runtime_lock_text
        if runtime_lock_text is not None
        else RUNTIME_LOCK.read_text(encoding="utf-8")
    )
    if policy.get("schema_version") != "lotus-pip-audit-exceptions.v1":
        errors.append("policy schema_version must be lotus-pip-audit-exceptions.v1")
    exceptions = policy.get("exceptions")
    if not isinstance(exceptions, list):
        errors.append("policy exceptions must be a list")
        return errors

    seen: set[str] = set()
    for index, exception in enumerate(exceptions):
        if not isinstance(exception, dict):
            errors.append(f"exception {index} must be an object")
            continue
        missing = sorted(REQUIRED_FIELDS - set(exception))
        if missing:
            errors.append(f"exception {index} missing fields: {', '.join(missing)}")
        advisory_id = str(exception.get("advisory_id", ""))
        if not advisory_id:
            errors.append(f"exception {index} advisory_id is required")
        elif advisory_id in seen:
            errors.append(f"exception {advisory_id} is duplicated")
        seen.add(advisory_id)
        try:
            review_by = date.fromisoformat(str(exception.get("review_by", "")))
        except ValueError:
            errors.append(f"exception {advisory_id or index} review_by must be YYYY-MM-DD")
        else:
            if review_by < effective_today:
                errors.append(f"exception {advisory_id} expired on {review_by.isoformat()}")
        dependency_constraint = str(exception.get("dependency_constraint", ""))
        if dependency_constraint and dependency_constraint not in lock_text:
            errors.append(
                f"exception {advisory_id} dependency constraint is no longer present: "
                f"{dependency_constraint}"
            )
        controls = exception.get("compensating_controls")
        if not isinstance(controls, list) or not controls or not all(controls):
            errors.append(f"exception {advisory_id or index} compensating_controls must be set")
    return errors


def ignore_args(policy: dict[str, Any]) -> list[str]:
    args: list[str] = []
    for exception in policy["exceptions"]:
        args.extend(["--ignore-vuln", str(exception["advisory_id"])])
    return args


def main() -> int:
    parser = argparse.ArgumentParser(description="Run governed pip-audit for lotus-archive.")
    parser.add_argument("--check-only", action="store_true", help="Validate exception policy only.")
    args = parser.parse_args()

    policy = load_policy()
    errors = validate_policy(policy)
    if errors:
        for error in errors:
            print(f"security-audit policy error: {error}", file=sys.stderr)
        return 1
    if args.check_only:
        print("pip-audit exception policy valid")
        return 0

    command = [
        sys.executable,
        "-m",
        "pip_audit",
        *ignore_args(policy),
        "-r",
        str(RUNTIME_LOCK),
        "-r",
        str(CI_LOCK),
    ]
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
