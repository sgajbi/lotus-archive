"""Registered API component journey, not actual producer/network qualification."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.archive.api import archive_service
from app.main import app
from tests.integration.test_archive_documents_api import _service
from tests.integration.test_composite_pooled_custody import pooled_custody_journey


def test_pooled_custody_consumer_journey(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            pooled_custody_journey((api, service))
    finally:
        app.dependency_overrides.clear()
