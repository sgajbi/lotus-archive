"""Required PG: retained v1-v5, v6 forward migration/refusals and fresh readers."""

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
from tests.fixtures.composite_amendment import SELECTIONS, amendment_payload
from tests.fixtures.composite_pooled import CASES
from tests.fixtures.composite_workbook import workbook_bytes
from tests.integration.test_archive_documents_api import _headers
from tests.integration.test_composite_amendment_custody import (
    amendment_custody_journey,
    amendment_headers,
)
from tests.integration.test_composite_custody_api import payload
from tests.integration.test_composite_eligibility_custody import eligibility_custody_journey
from tests.integration.test_composite_linked_custody import linked_custody_journey
from tests.integration.test_composite_pooled_custody import pooled_custody_journey, pooled_headers
from tests.integration.test_composite_v2_custody import v2_custody_journey
from tests.integration.test_postgres_document_scope_authorization import _postgres_service

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = required_database_url()
ROWS = "SELECT document_id, to_jsonb(d) FROM archive_documents d ORDER BY document_id"
CONSTRAINT = "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='archive_documents'::regclass AND conname='archive_documents_scope_check'"


def _reject_premature_admission(connection: psycopg.Connection, document_id: str) -> None:
    offered = amendment_payload()["metadata"]
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
                    json.dumps(offered[k]) if k == "composite_report_identity" else offered[k]
                    for k in keys
                ],
                document_id,
            ),
        )


def _assert_raw_refusals(connection: psycopg.Connection, document_id: str) -> None:
    before = connection.execute(ROWS).fetchall()
    guard = connection.execute(CONSTRAINT).fetchone()
    for old in sorted((ROOT / "migrations").glob("0[12][45678]_*.sql")):
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(old.read_text())
        assert connection.execute(ROWS).fetchall() == before
        assert connection.execute(CONSTRAINT).fetchone() == guard
    for assignment in (
        "composite_report_identity=NULL",
        "template_version='v5'",
        "tenant_id='foreign'",
        "composite_report_identity=jsonb_set(composite_report_identity,'{qualification}','\"CONTROLLED_ELIGIBILITY_SOURCE_REPLAY\"')",
        "composite_report_identity=jsonb_set(composite_report_identity,'{selection,selection_version}','\"v1\"')",
        "composite_report_identity=composite_report_identity #- '{selection,selection_version}'",
        "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months,0,lineage_receipts}','[]')",
        "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months,0,lineage_receipts}','null')",
        "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months,0,lineage_receipts}','true')",
        "composite_report_identity=composite_report_identity #- '{selection,months,0,lineage_receipts,0,receipt_response_digest}'",
        "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months,0,lineage_receipts,0,product_version}','\"v3\"')",
        "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months,0,lineage_receipts,0,evaluation_revision}','\" \"')",
        "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months,0,parent_publication_response_digest}','null')",
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                f"UPDATE archive_documents SET {assignment} WHERE document_id=%s", (document_id,)
            )
        assert connection.execute(ROWS).fetchall() == before


def test_populated_v6_upgrade_preserves_v1_v5_and_reopens_all_lineage(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        existing = connection.execute("SELECT to_regclass('archive_documents')").fetchone()
        if existing and existing[0]:
            connection.execute("TRUNCATE archive_documents CASCADE")
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            if int(migration.name.split("_", 1)[0]) < 19:
                connection.execute(migration.read_text())
        connection.execute("TRUNCATE archive_access_audit")
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            created = api.post(
                "/documents", json=payload(workbook_bytes()), headers=_headers("lotus-render")
            )
            assert created.status_code == 201
            legacy = [
                created.json(),
                *v2_custody_journey((api, service)),
                *linked_custody_journey((api, service)),
                *eligibility_custody_journey((api, service), "PUBLISHED"),
                *eligibility_custody_journey((api, service), "EVALUATED_ONLY"),
            ]
            pooled = pooled_custody_journey((api, service))
            with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
                before = connection.execute(ROWS).fetchall()
                assert len(before) == 19
                _reject_premature_admission(connection, legacy[0]["document_id"])
                assert connection.execute(ROWS).fetchall() == before
                migration = ROOT / "migrations/019_add_composite_amendment_custody.sql"
                connection.execute(migration.read_text())
                connection.execute(migration.read_text())
                assert connection.execute(ROWS).fetchall() == before
            refreshed = []
            for case in SELECTIONS:
                records = amendment_custody_journey((api, service), case)
                for variant, record in zip(
                    ("original", "technical", "corrected"), records, strict=True
                ):
                    held = api.get(
                        f"/documents/{record['document_id']}", headers=amendment_headers()
                    ).json()
                    refreshed.append((case, variant, held, records[-1]["document_id"]))
            pooled_refreshed = [
                (case, api.get(f"/documents/{row['document_id']}", headers=pooled_headers()).json())
                for case, row in zip(CASES, pooled, strict=True)
            ]
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            assert len(connection.execute(ROWS).fetchall()) == 31
            _assert_raw_refusals(connection, refreshed[0][2]["document_id"])
        new_evidence = tmp_path / "amendment-reopen.json"
        new_evidence.write_text(json.dumps(refreshed))
        old_evidence = tmp_path / "pooled-reopen.json"
        old_evidence.write_text(json.dumps(pooled_refreshed))
        for module, arguments, count in (
            (
                "tests.fixtures.composite_eligibility_restart_probe",
                [row["document_id"] for row in legacy],
                11,
            ),
            ("tests.fixtures.composite_pooled_restart_probe", [str(old_evidence)], 8),
            ("tests.fixtures.composite_amendment_restart_probe", [str(new_evidence)], 12),
        ):
            probe = subprocess.run(
                [sys.executable, "-m", module, str(tmp_path), *arguments],
                cwd=ROOT,
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            assert probe.returncode == 0, probe.stdout + probe.stderr
            result = json.loads(probe.stdout.splitlines()[-1])
            assert result["reopened"] == count and result["pid"] != os.getpid()
    finally:
        app.dependency_overrides.clear()
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute("TRUNCATE archive_documents CASCADE")
