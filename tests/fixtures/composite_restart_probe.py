"""Child-process probe used by the real PostgreSQL upgrade integration test."""

from base64 import b64encode
import json
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient

from app.archive.api import archive_service
from app.main import app
from tests.fixtures.composite_workbook import workbook_bytes
from tests.integration.test_archive_documents_api import _headers
from tests.integration.test_composite_custody_api import payload
from tests.integration.test_composite_v2_custody import v2_headers, v2_payload
from tests.integration.test_postgres_document_scope_authorization import _postgres_service


def main() -> None:
    root, legacy, original, corrected = sys.argv[1:]
    service = _postgres_service(Path(root))
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            cases = (
                (legacy, payload(workbook_bytes()), _headers()),
                (original, v2_payload(), v2_headers()),
                (corrected, v2_payload(corrected=True), v2_headers()),
            )
            for document_id, offered, headers in cases:
                record = api.get(f"/documents/{document_id}", headers=headers)
                assert record.status_code == 200
                assert (
                    record.json()["composite_report_identity"]
                    == offered["metadata"]["composite_report_identity"]
                )
                retry = api.post(
                    "/documents",
                    json=offered,
                    headers={**headers, "X-Caller-Service": "lotus-render"},
                )
                assert retry.status_code == 201 and retry.json() == record.json()
                downloaded = api.get(f"/documents/{document_id}/download", headers=headers)
                assert downloaded.status_code == 200
                assert b64encode(downloaded.content).decode("ascii") == offered["content_base64"]
            current = api.get(f"/documents/{original}/current", headers=v2_headers())
            assert current.json()["document_id"] == corrected
    finally:
        app.dependency_overrides.clear()
    print(json.dumps({"reopened": 3, "pid": os.getpid()}))


if __name__ == "__main__":
    main()
