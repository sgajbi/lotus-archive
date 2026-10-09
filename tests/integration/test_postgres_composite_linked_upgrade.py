"""Real populated 014+015 upgrade: preserved rows, atomic refusals and reopen."""

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
from tests.fixtures.composite_linked import linked_payload
from tests.fixtures.composite_workbook import workbook_bytes
from tests.integration.test_archive_documents_api import _headers
from tests.integration.test_composite_custody_api import payload
from tests.integration.test_composite_linked_custody import linked_custody_journey
from tests.integration.test_composite_v2_custody import v2_custody_journey
from tests.integration.test_postgres_document_scope_authorization import _postgres_service

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = required_database_url()
ROWS = "SELECT document_id, to_jsonb(d) FROM archive_documents d ORDER BY document_id"
CONSTRAINT = "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='archive_documents'::regclass AND conname='archive_documents_scope_check'"


def test_populated_v1_v2_linked_upgrade_atomic_guards_and_process_reopen(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        existing = connection.execute("SELECT to_regclass('archive_documents')").fetchone()
        if existing and existing[0]:
            connection.execute("TRUNCATE archive_documents CASCADE")
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            if int(migration.name.split("_", 1)[0]) >= 16:
                continue
            connection.execute(migration.read_text())
        connection.execute("TRUNCATE archive_access_audit")
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            response = api.post(
                "/documents", json=payload(workbook_bytes()), headers=_headers("lotus-render")
            )
            assert response.status_code == 201, response.text
            legacy = response.json()
            v2_original, v2_corrected = v2_custody_journey((api, service))
            with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
                before = connection.execute(ROWS).fetchall()
                # The existing guard truly refuses the new shape, even though
                # the strict application contract now accepts it.
                offered = linked_payload()["metadata"]
                patch = {
                    key: offered[key]
                    for key in (
                        "tenant_id",
                        "composite_id",
                        "reporting_period_start",
                        "reporting_period_end",
                        "as_of_date",
                        "template_version",
                        "report_data_contract_version",
                        "composite_report_identity",
                    )
                }
                with pytest.raises(psycopg.errors.CheckViolation):
                    connection.execute(
                        "UPDATE archive_documents SET tenant_id=%s, composite_id=%s, reporting_period_start=%s, reporting_period_end=%s, as_of_date=%s, template_version=%s, report_data_contract_version=%s, composite_report_identity=%s::jsonb WHERE document_id=%s",
                        (
                            *[
                                json.dumps(value) if key == "composite_report_identity" else value
                                for key, value in patch.items()
                            ],
                            v2_original["document_id"],
                        ),
                    )
                assert connection.execute(ROWS).fetchall() == before
                migration = ROOT / "migrations/016_add_composite_linked_custody.sql"
                connection.execute(migration.read_text())
                connection.execute(migration.read_text())
                assert connection.execute(ROWS).fetchall() == before
            original, corrected = linked_custody_journey((api, service))
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            before = connection.execute(ROWS).fetchall()
            guard = connection.execute(CONSTRAINT).fetchone()
            assert len(before) == 5
            for old in ("014_add_composite_report_scope.sql", "015_add_composite_v2_custody.sql"):
                with pytest.raises(psycopg.errors.CheckViolation):
                    connection.execute((ROOT / "migrations" / old).read_text())
                assert connection.execute(ROWS).fetchall() == before
                assert connection.execute(CONSTRAINT).fetchone() == guard
            for assignment in (
                "template_version='v2'",
                "report_data_contract_version='composite_review.v2'",
                "tenant_id='foreign'",
                "composite_id='foreign'",
                "portfolio_id='invented'",
                "composite_report_identity=jsonb_set(composite_report_identity,'{publication_state}','\"APPROVED\"')",
                "composite_report_identity=jsonb_set(composite_report_identity,'{selection,source_request,method}','\"OTHER\"')",
                "composite_report_identity=jsonb_set(composite_report_identity,'{selection,source_request,restatement_sequence}','1')",
                "composite_report_identity=jsonb_set(composite_report_identity,'{selection,source_request,metric_id}','\"TWR\"')",
                "composite_report_identity=jsonb_set(composite_report_identity,'{selection,source_request,materialization_ids}','[]')",
                "composite_report_identity=jsonb_set(composite_report_identity,'{selection,source_request,period_end}','\"2026-03-01\"')",
                "composite_report_identity=jsonb_set(composite_report_identity,'{selection,windows}','[]')",
                "composite_report_identity=jsonb_set(composite_report_identity,'{selection,windows}','{}')",
                "composite_report_identity=jsonb_set(composite_report_identity,'{selection,windows}','null')",
                "composite_report_identity=jsonb_set(composite_report_identity,'{source_products}','[]')",
            ):
                with pytest.raises(psycopg.errors.CheckViolation):
                    connection.execute(
                        f"UPDATE archive_documents SET {assignment} WHERE document_id=%s",
                        (original["document_id"],),
                    )
                assert connection.execute(ROWS).fetchall() == before
            # Corrupt INSERT cannot evade the same guard through NULL semantics.
            with pytest.raises(psycopg.errors.CheckViolation):
                connection.execute(
                    "INSERT INTO archive_documents SELECT (jsonb_populate_record(NULL::archive_documents, to_jsonb(d) || %s::jsonb)).* FROM archive_documents d WHERE document_id=%s",
                    (
                        json.dumps(
                            {
                                "document_id": "corrupt-linked-insert",
                                "archive_request_id": "corrupt-linked-insert",
                                "composite_report_identity": None,
                            }
                        ),
                        original["document_id"],
                    ),
                )
            assert connection.execute(ROWS).fetchall() == before
        probe = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.fixtures.composite_linked_restart_probe",
                str(tmp_path),
                legacy["document_id"],
                v2_original["document_id"],
                v2_corrected["document_id"],
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
        assert result["reopened"] == 5 and result["pid"] != os.getpid()
    finally:
        app.dependency_overrides.clear()
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute("TRUNCATE archive_documents CASCADE")
