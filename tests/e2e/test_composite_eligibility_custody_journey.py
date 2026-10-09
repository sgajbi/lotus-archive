"""Registered consumer journey; synthetic component transport, not joined proof."""

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.archive.api import archive_service
from app.main import app
from tests.integration.test_archive_documents_api import _service
from tests.integration.test_composite_eligibility_custody import eligibility_custody_journey


@pytest.mark.parametrize("kind", ["PUBLISHED", "EVALUATED_ONLY"])
def test_eligibility_custody_consumer_journey(tmp_path: Path, kind: str) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            eligibility_custody_journey((api, service), kind)
    finally:
        app.dependency_overrides.clear()
