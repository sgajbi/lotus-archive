"""Fresh-process PostgreSQL/object reads after a populated v4 upgrade."""

from base64 import b64encode
import json
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient

from app.archive.api import archive_service
from app.main import app
from tests.fixtures.composite_eligibility import eligibility_payload
from tests.fixtures.composite_linked import linked_payload
from tests.fixtures.composite_workbook import workbook_bytes
from tests.integration.test_archive_documents_api import _headers
from tests.integration.test_composite_custody_api import payload
from tests.integration.test_composite_linked_custody import linked_headers
from tests.integration.test_composite_v2_custody import v2_headers, v2_payload
from tests.integration.test_postgres_document_scope_authorization import _postgres_service


def main() -> None:
    root, *identifiers = sys.argv[1:]
    assert len(identifiers) == 11
    cases = [
        (payload(workbook_bytes()), _headers()),
        (v2_payload(), v2_headers()),
        (v2_payload(corrected=True), v2_headers()),
        (linked_payload(), linked_headers()),
        (linked_payload(corrected=True), linked_headers()),
        *[
            (eligibility_payload(kind, variant), linked_headers())
            for kind in ("PUBLISHED", "EVALUATED_ONLY")
            for variant in ("original", "technical", "corrected")
        ],
    ]
    service = _postgres_service(Path(root))
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            for document_id, (offered, headers) in zip(identifiers, cases):
                route = f"/documents/{document_id}"
                record = api.get(route, headers=headers)
                assert record.status_code == 200
                assert (
                    record.json()["composite_report_identity"]
                    == offered["metadata"]["composite_report_identity"]
                )
                replay = api.post(
                    "/documents",
                    json=offered,
                    headers={**headers, "X-Caller-Service": "lotus-render"},
                )
                assert replay.status_code == 201 and replay.json() == record.json()
                downloaded = api.get(route + "/download", headers=headers)
                assert downloaded.status_code == 200
                assert b64encode(downloaded.content).decode("ascii") == offered["content_base64"]
                events = api.get(route + "/source-events", headers=headers)
                assert (
                    events.status_code == 200
                    and events.json()["events"][0]["composite_report_identity"]
                    == record.json()["composite_report_identity"]
                )
                assert api.get(route + "/retention", headers=headers).status_code == 200
                assert (
                    api.get(
                        route, headers={**headers, "X-Tenant-Id": "foreign-reopened"}
                    ).status_code
                    == 403
                )
            for index, target in ((1, 2), (3, 4), (5, 7), (6, 7), (8, 10), (9, 10)):
                assert (
                    api.get(
                        f"/documents/{identifiers[index]}/current", headers=cases[index][1]
                    ).json()["document_id"]
                    == identifiers[target]
                )
    finally:
        app.dependency_overrides.clear()
    print(json.dumps({"reopened": 11, "pid": os.getpid()}))


if __name__ == "__main__":
    main()
