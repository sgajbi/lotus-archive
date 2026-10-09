"""Registered composite artifact creation-to-retained-correction product journey."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.archive.api import archive_service
from app.main import app
from tests.integration.test_archive_documents_api import _service
from tests.integration.test_composite_custody_api import composite_custody_journey


def test_registered_composite_retained_artifact_journey(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as client:
            composite_custody_journey((client, service), tmp_path)
    finally:
        app.dependency_overrides.clear()
