"""Full service/filesystem path with synthetic bytes, not joined source proof."""

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.archive.api import archive_service
from app.main import app
from tests.fixtures.composite_amendment import SELECTIONS
from tests.integration.test_archive_documents_api import _service
from tests.integration.test_composite_amendment_custody import amendment_custody_journey


@pytest.mark.parametrize("case", SELECTIONS)
def test_complete_amendment_document_lifecycle(tmp_path: Path, case: str) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            amendment_custody_journey((api, service), case)
    finally:
        app.dependency_overrides.clear()
