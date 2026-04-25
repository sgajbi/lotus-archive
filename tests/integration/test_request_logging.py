import json
import logging

from fastapi.testclient import TestClient
import pytest

from app.main import app


def test_request_log_is_structured_and_support_safe(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="lotus_archive.requests")

    client = TestClient(app)
    response = client.get("/health", headers={"X-Correlation-Id": "corr-log"})

    assert response.status_code == 200
    messages = [
        record.message for record in caplog.records if record.name == "lotus_archive.requests"
    ]
    assert messages
    event = json.loads(messages[-1])
    assert event["event"] == "request_completed"
    assert event["service"] == "lotus-archive"
    assert event["correlation_id"] == "corr-log"
    assert event["path"] == "/health"
    assert "bucket" not in messages[-1].lower()
    assert "storage_key" not in messages[-1].lower()
