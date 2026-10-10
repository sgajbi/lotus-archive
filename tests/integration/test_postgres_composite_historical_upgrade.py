"""Required PostgreSQL: populated forward upgrade, raw refusal and fresh reader."""

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
from tests.fixtures.composite_amendment import amendment_payload
from tests.fixtures.composite_historical import IDENTITIES, historical_payload
from tests.integration.test_composite_amendment_custody import amendment_headers
from tests.integration.test_postgres_document_scope_authorization import _postgres_service

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = required_database_url()
ROWS = "SELECT document_id, to_jsonb(d) FROM archive_documents d ORDER BY document_id"


def test_historical_upgrade_preserves_v6_and_reopens_all_graph_cases(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        existing = connection.execute("SELECT to_regclass('archive_documents')").fetchone()
        if existing and existing[0]:
            connection.execute("TRUNCATE archive_documents CASCADE")
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            if int(migration.name.split("_", 1)[0]) < 20:
                connection.execute(migration.read_text())
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            legacy = api.post(
                "/documents", json=amendment_payload(), headers=amendment_headers("lotus-render")
            )
            assert legacy.status_code == 201, legacy.text
            with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
                before = connection.execute(ROWS).fetchall()
                identity = historical_payload("v1-root-published")["metadata"][
                    "composite_report_identity"
                ]
                with pytest.raises(psycopg.errors.CheckViolation):
                    connection.execute(
                        "UPDATE archive_documents SET template_version='v7', report_data_contract_version='composite_review.v7', composite_report_identity=%s::jsonb WHERE document_id=%s",
                        (json.dumps(identity), legacy.json()["document_id"]),
                    )
                assert connection.execute(ROWS).fetchall() == before
                migration = ROOT / "migrations/020_add_composite_historical_policy_custody.sql"
                connection.execute(migration.read_text())
                connection.execute(migration.read_text())
                assert connection.execute(ROWS).fetchall() == before
            records = []
            for case in IDENTITIES:
                response = api.post(
                    "/documents",
                    json=historical_payload(case),
                    headers=amendment_headers("lotus-render"),
                )
                assert response.status_code == 201, response.text
                records.append((case, response.json()))
            with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
                before = connection.execute(ROWS).fetchall()
                assert len(before) == 13
                document_id = next(
                    record["document_id"]
                    for case, record in records
                    if case == "v2-correction-3-published"
                )
                for assignment in (
                    "tenant_id='foreign'",
                    "template_version='v6'",
                    "composite_report_identity=composite_report_identity #- '{calculation_boundary}'",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{calculation_boundary}','\"BANK_VERIFIED\"')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,selection_version}','\"v2\"')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months,0,product_version}','\"v2\"')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months,0,lineage_receipts}','[]')",
                    "composite_report_identity=jsonb_set(composite_report_identity,'{selection,months,0,lineage_receipts,1,product_version}','\"v4\"')",
                    "composite_report_identity=composite_report_identity #- '{selection,months,0,lineage_receipts,0,receipt_response_digest}'",
                ):
                    with pytest.raises(psycopg.errors.CheckViolation):
                        connection.execute(
                            f"UPDATE archive_documents SET {assignment} WHERE document_id=%s",
                            (document_id,),
                        )
                    assert connection.execute(ROWS).fetchall() == before
                with pytest.raises(psycopg.errors.CheckViolation):
                    connection.execute(
                        (ROOT / "migrations/019_add_composite_amendment_custody.sql").read_text()
                    )
                assert connection.execute(ROWS).fetchall() == before
            evidence = tmp_path / "historical-reopen.json"
            evidence.write_text(json.dumps(records))
            probe = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tests.fixtures.composite_historical_restart_probe",
                    str(tmp_path),
                    str(evidence),
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
            assert result["reopened"] == 12 and result["pid"] != os.getpid()
    finally:
        app.dependency_overrides.clear()
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute("TRUNCATE archive_documents CASCADE")
