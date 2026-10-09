"""Populated legacy-to-v4 scope upgrade, atomic guard refusals and process reopen."""

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
from tests.fixtures.composite_eligibility import eligibility_payload
from tests.fixtures.composite_workbook import workbook_bytes
from tests.integration.test_archive_documents_api import _headers
from tests.integration.test_composite_custody_api import payload
from tests.integration.test_composite_eligibility_custody import eligibility_custody_journey
from tests.integration.test_composite_linked_custody import linked_custody_journey
from tests.integration.test_composite_v2_custody import v2_custody_journey
from tests.integration.test_postgres_document_scope_authorization import _postgres_service

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = required_database_url()
ROWS = "SELECT document_id, to_jsonb(d) FROM archive_documents d ORDER BY document_id"
CONSTRAINT = "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='archive_documents'::regclass AND conname='archive_documents_scope_check'"


def test_populated_legacy_upgrade_v4_refusals_and_fresh_process(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        existing = connection.execute("SELECT to_regclass('archive_documents')").fetchone()
        if existing and existing[0]:
            connection.execute("TRUNCATE archive_documents CASCADE")
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            if int(migration.name.split("_", 1)[0]) < 17:
                connection.execute(migration.read_text())
        connection.execute("TRUNCATE archive_access_audit")
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            created = api.post(
                "/documents", json=payload(workbook_bytes()), headers=_headers("lotus-render")
            )
            assert created.status_code == 201, created.text
            legacy = created.json()
            v2 = v2_custody_journey((api, service))
            v3 = linked_custody_journey((api, service))
            with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
                before = connection.execute(ROWS).fetchall()
                assert len(before) == 5
                offered = eligibility_payload()["metadata"]
                keys = (
                    "tenant_id",
                    "composite_id",
                    "reporting_period_start",
                    "reporting_period_end",
                    "as_of_date",
                    "template_version",
                    "report_data_contract_version",
                    "composite_report_identity",
                )
                with pytest.raises(psycopg.errors.CheckViolation):
                    connection.execute(
                        "UPDATE archive_documents SET tenant_id=%s, composite_id=%s, reporting_period_start=%s, reporting_period_end=%s, as_of_date=%s, template_version=%s, report_data_contract_version=%s, composite_report_identity=%s::jsonb WHERE document_id=%s",
                        (
                            *[
                                json.dumps(offered[key])
                                if key == "composite_report_identity"
                                else offered[key]
                                for key in keys
                            ],
                            legacy["document_id"],
                        ),
                    )
                assert connection.execute(ROWS).fetchall() == before
                migration = ROOT / "migrations/017_add_composite_eligibility_custody.sql"
                connection.execute(migration.read_text())
                connection.execute(migration.read_text())
                assert connection.execute(ROWS).fetchall() == before
            published = eligibility_custody_journey((api, service), "PUBLISHED")
            evaluated = eligibility_custody_journey((api, service), "EVALUATED_ONLY")
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            before = connection.execute(ROWS).fetchall()
            guard = connection.execute(CONSTRAINT).fetchone()
            assert len(before) == 11
            for old in (
                "014_add_composite_report_scope.sql",
                "015_add_composite_v2_custody.sql",
                "016_add_composite_linked_custody.sql",
            ):
                with pytest.raises(psycopg.errors.CheckViolation):
                    connection.execute((ROOT / "migrations" / old).read_text())
                assert connection.execute(ROWS).fetchall() == before
                assert connection.execute(CONSTRAINT).fetchone() == guard
            for document in (published[0], evaluated[0]):
                for assignment in (
                    "template_version='v3'",
                    "report_data_contract_version='composite_review.v3'",
                    "tenant_id='foreign'",
                    "composite_id='foreign'",
                    "portfolio_id='invented'",
                    "composite_report_identity=NULL",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{publication_state}','\"ATTESTED\"')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{qualification}','\"EXPLICIT_RETAINED_CALCULATED_REPLAY\"')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,reporting_currency}','\"usd\"')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,definition_version}','\"\"')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,period_end}','\"2026-02-28\"')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months}','[]')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months}','{}')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months}','null')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months,0,evidence_kind}','\"APPROVED\"')",
                    "composite_report_identity=composite_report_identity #- '{selection,months,0,evidence_kind}'",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months,0,evidence_kind}','null')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months,0,evidence_kind}','true')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months,0,month}','\"2026-02\"')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,calculation_id}','\"fake\"')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{source_products}','[]')",
                ):
                    with pytest.raises(psycopg.errors.CheckViolation):
                        connection.execute(
                            f"UPDATE archive_documents SET {assignment} WHERE document_id=%s",
                            (document["document_id"],),
                        )
                    assert connection.execute(ROWS).fetchall() == before
                with pytest.raises(psycopg.errors.CheckViolation):
                    connection.execute(
                        "INSERT INTO archive_documents SELECT (jsonb_populate_record(NULL::archive_documents, to_jsonb(d) || %s::jsonb)).* FROM archive_documents d WHERE document_id=%s",
                        (
                            json.dumps(
                                {
                                    "document_id": "corrupt-v4-insert",
                                    "archive_request_id": "corrupt-v4-insert",
                                    "composite_report_identity": None,
                                }
                            ),
                            document["document_id"],
                        ),
                    )
                assert connection.execute(ROWS).fetchall() == before
        identifiers = [
            legacy["document_id"],
            *[row["document_id"] for row in (*v2, *v3, *published, *evaluated)],
        ]
        probe = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.fixtures.composite_eligibility_restart_probe",
                str(tmp_path),
                *identifiers,
            ],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert probe.returncode == 0, probe.stdout + probe.stderr
        result = json.loads(probe.stdout.splitlines()[-1])
        assert result["reopened"] == 11 and result["pid"] != os.getpid()
    finally:
        app.dependency_overrides.clear()
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute("TRUNCATE archive_documents CASCADE")
