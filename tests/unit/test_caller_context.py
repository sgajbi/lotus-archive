import pytest

from app.security.caller_context import CallerContextMissingError, caller_context_from_headers


def test_caller_context_from_headers_parses_required_support_context() -> None:
    context = caller_context_from_headers(
        {
            "X-Caller-Service": "lotus-report",
            "X-Actor-Type": "service",
            "X-Actor-Id": "report-worker",
        },
        correlation_id="corr-123",
    )

    assert context.caller_service == "lotus-report"
    assert context.actor_type == "service"
    assert context.actor_id == "report-worker"
    assert context.correlation_id == "corr-123"


def test_caller_context_from_headers_reports_missing_fields() -> None:
    with pytest.raises(CallerContextMissingError) as exc_info:
        caller_context_from_headers({"X-Caller-Service": "lotus-report"}, correlation_id="corr-123")

    assert exc_info.value.missing_headers == ("x-actor-type", "x-actor-id")
