"""Populated 014-to-015 upgrade and actual separate-process repository reopen."""

import json
import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import psycopg
import pytest

from app.archive.api import archive_service
from app.main import app
from tests.database_proof import required_database_url
from tests.fixtures.composite_workbook import workbook_bytes
from tests.integration.test_archive_documents_api import _headers
from tests.integration.test_composite_custody_api import payload
from tests.integration.test_composite_v2_custody import v2_custody_journey
from tests.integration.test_postgres_document_scope_authorization import _postgres_service

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = required_database_url()


def test_populated_v1_upgrade_v2_refusals_and_process_reopen(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        existing = connection.execute("SELECT to_regclass('archive_documents')").fetchone()
        if existing and existing[0]:
            connection.execute("TRUNCATE archive_documents CASCADE")
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            if migration.name.startswith("015_"):
                continue
            connection.execute(migration.read_text())
        connection.execute("TRUNCATE archive_access_audit")
        connection.execute(
            "TRUNCATE archive_lifecycle_relationships, archive_legal_holds, archive_documents"
        )
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            offered = payload(workbook_bytes())
            created = api.post("/documents", json=offered, headers=_headers("lotus-render"))
            assert created.status_code == 201, created.text
            legacy = created.json()
            with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
                before = connection.execute(
                    "SELECT to_jsonb(d) FROM archive_documents d WHERE document_id = %s",
                    (legacy["document_id"],),
                ).fetchone()
                migration = ROOT / "migrations/015_add_composite_v2_custody.sql"
                connection.execute(migration.read_text())
                connection.execute(migration.read_text())
                after = connection.execute(
                    "SELECT to_jsonb(d) FROM archive_documents d WHERE document_id = %s",
                    (legacy["document_id"],),
                ).fetchone()
                assert after == before
            assert (
                api.post("/documents", json=offered, headers=_headers("lotus-render")).json()
                == legacy
            )
            original, corrected = v2_custody_journey((api, service))
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            retained_query = (
                "SELECT document_id, to_jsonb(d) FROM archive_documents d ORDER BY document_id"
            )
            constraint_query = (
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='archive_documents'::regclass "
                "AND conname='archive_documents_scope_check'"
            )
            retained_before = connection.execute(retained_query).fetchall()
            constraint_before = connection.execute(constraint_query).fetchone()
            # An unsafe rollback to the historical v1-only constraint must fail
            # atomically, keeping all retained v1/v2 rows and the compatible guard.
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    (ROOT / "migrations/014_add_composite_report_scope.sql").read_text()
                )
            assert connection.execute(retained_query).fetchall() == retained_before
            assert connection.execute(constraint_query).fetchone() == constraint_before
            connection.execute(migration.read_text())
            oversized = (
                "jsonb_build_array("
                + ", ".join(["composite_report_identity->'source_products'->0"] * 9)
                + ")"
            )
            for assignment in (
                "template_version = 'v1'",
                "report_data_contract_version = 'composite_review.v1'",
                "portfolio_id = 'invented-portfolio'",
                "composite_report_identity = jsonb_set(composite_report_identity, '{source_products}', '[]')",
                "composite_report_identity = jsonb_set(composite_report_identity, '{source_products}', '{}')",
                f"composite_report_identity = jsonb_set(composite_report_identity, '{{source_products}}', {oversized})",
                "composite_report_identity = jsonb_set(composite_report_identity, '{publication_state}', '\"APPROVED\"')",
                "composite_report_identity = jsonb_set(composite_report_identity, '{contract_version}', '\"composite_review.v3\"')",
            ):
                with pytest.raises(psycopg.errors.CheckViolation):
                    connection.execute(
                        f"UPDATE archive_documents SET {assignment} WHERE document_id = %s",
                        (original["document_id"],),
                    )
        probe = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.fixtures.composite_restart_probe",
                str(tmp_path),
                legacy["document_id"],
                original["document_id"],
                corrected["document_id"],
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        assert probe.returncode == 0, probe.stdout + probe.stderr
        result = json.loads(probe.stdout.splitlines()[-1])
        assert result["reopened"] == 3 and result["pid"] != os.getpid()
    finally:
        app.dependency_overrides.clear()
        # Historical migration 014 deliberately remains v1-only. Do not leave
        # v2 test rows for another test's fresh-schema replay of that history.
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute("TRUNCATE archive_documents CASCADE")
