"""Frozen source identity through the owning Archive HTTP custody journey."""

from pathlib import Path

from fastapi.testclient import TestClient

from app.archive.api import archive_service
from app.main import app
from tests.integration.test_archive_documents_api import _service
from tests.integration.test_composite_v2_custody import v2_custody_journey


def test_v2_custody_keeps_retained_original_and_corrected_source_identity(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as client:
            v2_custody_journey((client, service))
    finally:
        app.dependency_overrides.clear()
