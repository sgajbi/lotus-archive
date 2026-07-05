from datetime import date

from scripts.security_audit import ignore_args, load_policy, validate_policy


def test_pip_audit_exception_policy_is_structured_and_current() -> None:
    policy = load_policy()
    errors = validate_policy(
        policy,
        today=date(2026, 7, 5),
        runtime_lock_text="prometheus-fastapi-instrumentator==7.1.0\n",
    )

    assert errors == []
    args = ignore_args(policy)
    assert "--ignore-vuln" in args
    assert "CVE-2026-48818" in args
    assert "PYSEC-2026-161" in args


def test_pip_audit_exception_policy_rejects_expired_exception() -> None:
    policy = load_policy()
    policy["exceptions"][0]["review_by"] = "2026-01-01"

    errors = validate_policy(
        policy,
        today=date(2026, 7, 5),
        runtime_lock_text="prometheus-fastapi-instrumentator==7.1.0\n",
    )

    assert any("expired" in error for error in errors)


def test_pip_audit_exception_policy_rejects_missing_constraint() -> None:
    policy = load_policy()

    errors = validate_policy(
        policy,
        today=date(2026, 7, 5),
        runtime_lock_text="prometheus-fastapi-instrumentator==8.0.0\n",
    )

    assert any("dependency constraint is no longer present" in error for error in errors)


def test_pip_audit_exception_policy_rejects_missing_required_field() -> None:
    policy = load_policy()
    del policy["exceptions"][0]["owner"]

    errors = validate_policy(
        policy,
        today=date(2026, 7, 5),
        runtime_lock_text="prometheus-fastapi-instrumentator==7.1.0\n",
    )

    assert any("missing fields: owner" in error for error in errors)
