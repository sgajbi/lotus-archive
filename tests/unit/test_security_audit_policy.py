from datetime import date
from pathlib import Path
import tomllib
from typing import Any

from scripts.security_audit import ignore_args, load_policy, validate_policy

ROOT = Path(__file__).resolve().parents[2]


def test_pip_audit_exception_policy_is_structured_and_current() -> None:
    policy = load_policy()
    errors = validate_policy(
        policy,
        today=date(2026, 7, 5),
        runtime_lock_text="prometheus-fastapi-instrumentator==8.0.2\nstarlette==1.3.1\n",
    )

    assert errors == []
    args = ignore_args(policy)
    assert args == []


def test_pip_audit_exception_policy_rejects_expired_exception() -> None:
    policy: dict[str, Any] = {
        "schema_version": "lotus-pip-audit-exceptions.v1",
        "exceptions": [
            {
                "advisory_id": "CVE-2026-0001",
                "affected_package": "example",
                "severity": "high",
                "owner": "sgajbi",
                "review_by": "2026-01-01",
                "rationale": "test",
                "dependency_constraint": "example==1.0.0",
                "removal_condition": "test",
                "compensating_controls": ["test"],
            }
        ],
    }

    errors = validate_policy(
        policy,
        today=date(2026, 7, 5),
        runtime_lock_text="example==1.0.0\n",
    )

    assert any("expired" in error for error in errors)


def test_pip_audit_exception_policy_rejects_missing_constraint() -> None:
    policy: dict[str, Any] = {
        "schema_version": "lotus-pip-audit-exceptions.v1",
        "exceptions": [
            {
                "advisory_id": "CVE-2026-0001",
                "affected_package": "example",
                "severity": "high",
                "owner": "sgajbi",
                "review_by": "2026-12-31",
                "rationale": "test",
                "dependency_constraint": "example==1.0.0",
                "removal_condition": "test",
                "compensating_controls": ["test"],
            }
        ],
    }

    errors = validate_policy(
        policy,
        today=date(2026, 7, 5),
        runtime_lock_text="prometheus-fastapi-instrumentator==8.0.0\n",
    )

    assert any("dependency constraint is no longer present" in error for error in errors)


def test_pip_audit_exception_policy_rejects_missing_required_field() -> None:
    policy: dict[str, Any] = {
        "schema_version": "lotus-pip-audit-exceptions.v1",
        "exceptions": [
            {
                "advisory_id": "CVE-2026-0001",
                "affected_package": "example",
                "severity": "high",
                "owner": "sgajbi",
                "review_by": "2026-12-31",
                "rationale": "test",
                "dependency_constraint": "example==1.0.0",
                "removal_condition": "test",
                "compensating_controls": ["test"],
            }
        ],
    }
    del policy["exceptions"][0]["owner"]

    errors = validate_policy(
        policy,
        today=date(2026, 7, 5),
        runtime_lock_text="example==1.0.0\n",
    )

    assert any("missing fields: owner" in error for error in errors)


def test_runtime_image_pins_starlette_above_known_fixed_versions() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = set(pyproject["project"]["dependencies"])
    dev_dependencies = set(pyproject["project"]["optional-dependencies"]["dev"])

    assert "fastapi==0.139.0" in dependencies
    assert "starlette==1.3.1" in dependencies
    assert "prometheus-fastapi-instrumentator==8.0.2" in dependencies
    assert "httpx2==2.5.0" in dev_dependencies
    assert "httpx==0.28.0" not in dev_dependencies
