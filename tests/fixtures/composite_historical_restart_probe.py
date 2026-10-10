"""Fresh PostgreSQL/filesystem historical reader; not disaster recovery."""

from base64 import b64decode
import json
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient

from app.archive.api import archive_service
from app.main import app
from tests.fixtures.composite_historical import historical_payload
from tests.integration.test_composite_amendment_custody import amendment_headers
from tests.integration.test_postgres_document_scope_authorization import _postgres_service


def main() -> None:
    root, evidence = sys.argv[1:]
    cases = json.loads(Path(evidence).read_text())
    assert len(cases) == 12
    app.dependency_overrides[archive_service] = lambda: _postgres_service(Path(root))
    try:
        with TestClient(app) as api:
            for case, record in cases:
                route = f"/documents/{record['document_id']}"
                held = api.get(route, headers=amendment_headers())
                assert held.status_code == 200 and held.json() == record
                offer = historical_payload(case)
                assert (
                    held.json()["composite_report_identity"]
                    == offer["metadata"]["composite_report_identity"]
                )
                download = api.get(route + "/download", headers=amendment_headers())
                assert download.status_code == 200 and download.content == b64decode(
                    offer["content_base64"]
                )
                assert api.get(route + "/retention", headers=amendment_headers()).status_code == 200
    finally:
        app.dependency_overrides.clear()
    print(json.dumps({"reopened": len(cases), "pid": os.getpid()}))


if __name__ == "__main__":
    main()
