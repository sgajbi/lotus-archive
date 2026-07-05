import json
import logging

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.middleware.correlation import (
    LOGGER,
    REQUEST_LOG_HANDLER_MARKER,
    configure_request_logging,
)


def test_request_logger_is_enabled_for_runtime_info_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    configure_request_logging()

    assert LOGGER.isEnabledFor(logging.INFO)
    assert any(getattr(handler, REQUEST_LOG_HANDLER_MARKER, False) for handler in LOGGER.handlers)


def test_request_log_is_structured_and_support_safe(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="lotus_archive.requests")

    client = TestClient(app)
    response = client.get(
        "/health",
        headers={"X-Correlation-Id": "corr-log", "X-Trace-Id": "trace-log"},
    )

    assert response.status_code == 200
    messages = [
        record.message for record in caplog.records if record.name == "lotus_archive.requests"
    ]
    assert messages
    event = json.loads(messages[-1])
    assert event["event"] == "request_completed"
    assert event["service"] == "lotus-archive"
    assert event["correlation_id"] == "corr-log"
    assert event["trace_id"] == "trace-log"
    assert event["path"] == "/health"
    assert "bucket" not in messages[-1].lower()
    assert "storage_key" not in messages[-1].lower()


def test_document_request_log_uses_route_template(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="lotus_archive.requests")

    client = TestClient(app)
    response = client.get(
        "/documents/doc_sensitive_123/download",
        headers={
            "X-Correlation-Id": "corr-log-doc",
            "X-Trace-Id": "trace-log-doc",
            "X-Caller-Service": "lotus-gateway",
            "X-Actor-Type": "service",
            "X-Actor-Id": "gateway-worker",
        },
    )

    assert response.status_code == 404
    messages = [
        record.message for record in caplog.records if record.name == "lotus_archive.requests"
    ]
    assert messages
    event = json.loads(messages[-1])
    assert event["path"] == "/documents/{document_id}/download"
    assert "doc_sensitive_123" not in messages[-1]
    assert event["correlation_id"] == "corr-log-doc"
    assert event["trace_id"] == "trace-log-doc"
