"""Required populated v1-v7 upgrade, direct SQL refusals, and fresh v8 reader."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg
import pytest

from app.archive.api import archive_service
from app.main import app
from tests.database_proof import required_database_url
from tests.fixtures.composite_amendment import amendment_payload
from tests.fixtures.composite_eligibility import eligibility_payload
from tests.fixtures.composite_historical import historical_payload
from tests.fixtures.composite_linked import linked_payload
from tests.fixtures.composite_pooled import pooled_payload
from tests.fixtures.composite_source_context import CASES, context_payload
from tests.fixtures.composite_workbook import workbook_bytes
from tests.integration.test_composite_custody_api import payload
from tests.integration.test_composite_source_context_custody import (
    context_custody_journey,
    context_headers,
)
from tests.integration.test_composite_v2_custody import v2_payload
from tests.integration.test_postgres_document_scope_authorization import _postgres_service

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = required_database_url()
ROWS = "SELECT document_id, to_jsonb(d) FROM archive_documents d ORDER BY document_id"
UPDATE = "UPDATE archive_documents SET composite_report_identity=%s::jsonb WHERE document_id=%s"
INSERT = """INSERT INTO archive_documents
SELECT (jsonb_populate_record(NULL::archive_documents, to_jsonb(d) || %s::jsonb)).*
FROM archive_documents d WHERE document_id=%s"""


def invalid_identities() -> list[dict[str, Any]]:
    original = context_payload()["metadata"]["composite_report_identity"]
    changes: list[tuple[tuple[str | int, ...], Any]] = [
        (("qualification",), "BANK_VERIFIED"),
        (("source_context",), None),
        (("source_context", "since_inception"), "true"),
        (("definition", "pin", "content_hash"), "invalid"),
        (("definition", "source_response_digest"), "sha256:" + "0" * 64),
        (("source_context", "definition", "definition_version"), "wrong"),
        (("source_context", "memberships", 0, "content_hash"), "invalid"),
        (("selection", "windows", 0, "definition_content_hash"), "sha256:" + "0" * 64),
        (("selection", "windows", 0, "membership_content_hash"), "sha256:" + "0" * 64),
        (("source_products",), None),
        (("source_products", 0, "pin", "kind"), "UNSUPPORTED"),
        (("source_products", 0, "pin", "selection", "reporting_currency"), "SGD"),
        (("source_products", 0, "source_response_digest"), "invalid"),
        (("source_products", 0, "pin", "year"), 2025),
        (("source_products", 0, "pin", "year"), "2026"),
        (("source_products", 1, "pin", "months"), 1),
        (("source_products", 1, "pin", "months"), "2"),
        (("source_products", 1, "pin", "selection", "windows", 0, "source_cut_id"), "changed"),
    ]
    results = []
    for path, value in changes:
        changed = deepcopy(original)
        cursor: Any = changed
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value
        results.append(changed)
    for path in (("source_context", "memberships"), ("source_products",), ("selection", "windows")):
        changed = deepcopy(original)
        cursor = changed
        for key in path:
            cursor = cursor[key]
        cursor.append(deepcopy(cursor[0]))
        results.append(changed)
    changed = deepcopy(original)
    changed.pop("definition")
    results.append(changed)
    return results


def test_populated_source_context_upgrade_and_reopen(tmp_path: Path) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        existing = connection.execute("SELECT to_regclass('archive_documents')").fetchone()
        if existing and existing[0]:
            connection.execute("TRUNCATE archive_documents CASCADE")
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            if int(migration.name.split("_", 1)[0]) < 21:
                connection.execute(migration.read_text())
    service = _postgres_service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            offers = [
                payload(workbook_bytes()),
                v2_payload(),
                linked_payload(),
                eligibility_payload(),
                pooled_payload(),
                amendment_payload(),
                historical_payload("v1-root-published"),
            ]
            records = []
            for offer in offers:
                response = api.post(
                    "/documents", json=offer, headers=context_headers(offer, "lotus-render")
                )
                assert response.status_code == 201, response.text
                records.append(response.json())
            with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
                before = connection.execute(ROWS).fetchall()
                assert len(before) == 7
                with pytest.raises(psycopg.errors.CheckViolation):
                    connection.execute(
                        "UPDATE archive_documents SET template_version='v8', report_data_contract_version='composite_review.v8', composite_report_identity=%s::jsonb WHERE document_id=%s",
                        (
                            json.dumps(context_payload()["metadata"]["composite_report_identity"]),
                            records[0]["document_id"],
                        ),
                    )
                assert connection.execute(ROWS).fetchall() == before
                migration = ROOT / "migrations/021_add_composite_source_context_custody.sql"
                connection.execute(migration.read_text())
                connection.execute(migration.read_text())
                assert connection.execute(ROWS).fetchall() == before
            records.extend(context_custody_journey((api, service)))
            offers.extend(context_payload(case) for case in CASES[:2])
            for case in CASES[2:]:
                offer = context_payload(case)
                response = api.post(
                    "/documents", json=offer, headers=context_headers(offer, "lotus-render")
                )
                assert response.status_code == 201, response.text
                records.append(response.json())
                offers.append(offer)
            with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
                before = connection.execute(ROWS).fetchall()
                assert len(before) == 11
                original = records[7]
                document_id = original["document_id"]
                # Valid direct writes exercise the same SQL paths as the bad controls.
                identity = offers[7]["metadata"]["composite_report_identity"]
                connection.execute(UPDATE, (json.dumps(identity), document_id))
                assert connection.execute(ROWS).fetchall() == before
                delta = {
                    "document_id": str(uuid4()),
                    "archive_request_id": str(uuid4()),
                    "storage_key": "sql-control-" + str(uuid4()),
                }
                with connection.transaction(force_rollback=True):
                    connection.execute(INSERT, (json.dumps(delta), document_id))
                    assert len(connection.execute(ROWS).fetchall()) == 12
                for changed in invalid_identities():
                    with pytest.raises(psycopg.errors.CheckViolation):
                        connection.execute(UPDATE, (json.dumps(changed), document_id))
                    with pytest.raises(psycopg.errors.CheckViolation):
                        connection.execute(
                            INSERT,
                            (
                                json.dumps({**delta, "composite_report_identity": changed}),
                                document_id,
                            ),
                        )
                    assert connection.execute(ROWS).fetchall() == before
                for assignment in (
                    "tenant_id='foreign'",
                    "template_version='v7'",
                    "portfolio_scope='portfolio'",
                ):
                    with pytest.raises(psycopg.errors.CheckViolation):
                        connection.execute(
                            f"UPDATE archive_documents SET {assignment} WHERE document_id=%s",
                            (document_id,),
                        )
                    assert connection.execute(ROWS).fetchall() == before
                with pytest.raises(psycopg.errors.CheckViolation):
                    connection.execute(
                        (
                            ROOT / "migrations/020_add_composite_historical_policy_custody.sql"
                        ).read_text()
                    )
                assert connection.execute(ROWS).fetchall() == before
            cases = []
            for offer, record in zip(offers, records, strict=True):
                route = f"/documents/{record['document_id']}"
                cases.append(
                    {
                        "offer": offer,
                        "record": api.get(route, headers=context_headers(offer)).json(),
                        "current_id": api.get(
                            route + "/current", headers=context_headers(offer)
                        ).json()["document_id"],
                    }
                )
            evidence = tmp_path / "source-context-reopen.json"
            evidence.write_text(json.dumps(cases))
            probe = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tests.fixtures.composite_source_context_restart_probe",
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
            assert result["reopened"] == 11 and result["pid"] != os.getpid()
    finally:
        app.dependency_overrides.clear()
        with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
            connection.execute("TRUNCATE archive_documents CASCADE")
