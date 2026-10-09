"""Fresh process reads all retained versions after the linked-custody upgrade."""

from base64 import b64encode
import json
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient

from app.archive.api import archive_service
from app.main import app
from tests.fixtures.composite_linked import linked_payload
from tests.fixtures.composite_workbook import workbook_bytes
from tests.integration.test_archive_documents_api import _headers
from tests.integration.test_composite_custody_api import payload
from tests.integration.test_composite_linked_custody import linked_headers
from tests.integration.test_composite_v2_custody import v2_headers, v2_payload
from tests.integration.test_postgres_document_scope_authorization import _postgres_service


def main() -> None:
    root, legacy, v2_original, v2_corrected, original, corrected = sys.argv[1:]
    service = _postgres_service(Path(root))
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            cases = (
                (legacy, payload(workbook_bytes()), _headers()),
                (v2_original, v2_payload(), v2_headers()),
                (v2_corrected, v2_payload(corrected=True), v2_headers()),
                (original, linked_payload(), linked_headers()),
                (corrected, linked_payload(corrected=True), linked_headers()),
            )
            for document_id, offered, headers in cases:
                route = f"/documents/{document_id}"
                record = api.get(route, headers=headers)
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
                download = api.get(route + "/download", headers=headers)
                assert download.status_code == 200
                assert b64encode(download.content).decode("ascii") == offered["content_base64"]
                events = api.get(route + "/source-events", headers=headers).json()
                assert (
                    events["events"][0]["composite_report_identity"]
                    == record.json()["composite_report_identity"]
                )
            for previous, current, headers in (
                (v2_original, v2_corrected, v2_headers()),
                (original, corrected, linked_headers()),
            ):
                assert (
                    api.get(f"/documents/{previous}/current", headers=headers).json()["document_id"]
                    == current
                )
    finally:
        app.dependency_overrides.clear()
    print(json.dumps({"reopened": 5, "pid": os.getpid()}))


if __name__ == "__main__":
    main()
