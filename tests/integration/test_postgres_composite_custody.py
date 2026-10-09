"""Real PostgreSQL plus filesystem API proof; required in governed CI lanes."""

from pathlib import Path

from fastapi.testclient import TestClient
import psycopg
import pytest

from app.archive.api import archive_service
from app.archive.exceptions import HistoricalIntegrityError
from app.main import app
from tests.database_proof import required_database_url
from tests.fixtures.composite_workbook import workbook_bytes
from tests.integration.test_archive_documents_api import _headers
from tests.integration.test_composite_custody_api import (
    payload,
    composite_custody_journey as custody_journey,
    test_corrupt_bytes_hash_conflicts_and_tenant_refusal as custody_refusals,
)
from tests.integration.test_postgres_document_scope_authorization import _postgres_service

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = required_database_url()


@pytest.fixture(autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            connection.execute(migration.read_text(encoding="utf-8"))
        connection.execute("TRUNCATE archive_access_audit")
        connection.execute(
            "TRUNCATE archive_lifecycle_relationships, archive_legal_holds, archive_documents"
        )


def test_real_postgres_custody_and_retained_correction(tmp_path: Path) -> None:
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            custody_journey((api, service), tmp_path)
    finally:
        app.dependency_overrides.clear()


def test_real_postgres_custody_refusals(tmp_path: Path) -> None:
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            custody_refusals((api, service))
    finally:
        app.dependency_overrides.clear()


def test_postgres_restart_lost_response_retry_preserves_identity_and_bytes(tmp_path: Path) -> None:
    offered = payload(workbook_bytes())
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            response = api.post("/documents", json=offered, headers=_headers("lotus-render"))
            assert response.status_code == 201
            original = response.json()
        restarted = _postgres_service(tmp_path)
        app.dependency_overrides[archive_service] = lambda: restarted
        with TestClient(app) as api:
            replay = api.post("/documents", json=offered, headers=_headers("lotus-render"))
            assert replay.status_code == 201 and replay.json() == original
            downloaded = api.get(
                f"/documents/{original['document_id']}/download", headers=_headers()
            )
            assert downloaded.status_code == 200 and downloaded.content == workbook_bytes()
            record = restarted.repository.get_by_document_id(original["document_id"])
            assert record is not None and record.composite_report_identity is not None
            assert (
                record.composite_report_identity.model_dump(mode="json")
                == original["composite_report_identity"]
            )
    finally:
        app.dependency_overrides.clear()


def test_postgres_scope_guard_and_immutable_source_pins(tmp_path: Path) -> None:
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            created = api.post(
                "/documents", json=payload(workbook_bytes()), headers=_headers("lotus-render")
            )
            assert created.status_code == 201
            document_id = created.json()["document_id"]
        stored = service.repository.get_by_document_id(document_id)
        assert stored is not None and stored.composite_report_identity is not None
        changed = stored.model_copy(deep=True)
        assert changed.composite_report_identity is not None
        changed.composite_report_identity.selection.windows[0].source_cut_id = "changed-cut"
        with pytest.raises(HistoricalIntegrityError):
            service.repository.save(changed)
        assert service.repository.get_by_document_id(document_id) == stored
        for statement in (
            "UPDATE archive_documents SET portfolio_id = 'fabricated-core' WHERE document_id = %s",
            "UPDATE archive_documents SET composite_report_identity = '{}'::jsonb WHERE document_id = %s",
            "UPDATE archive_documents SET composite_report_identity = jsonb_set(composite_report_identity, '{publication_state}', '\"APPROVED\"') WHERE document_id = %s",
        ):
            with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
                with pytest.raises(psycopg.errors.CheckViolation):
                    connection.execute(statement, (document_id,))
        assert service.repository.get_by_document_id(document_id) == stored
    finally:
        app.dependency_overrides.clear()
