"""Fresh PostgreSQL/filesystem reader of frozen legacy and v8 custody."""

from base64 import b64decode
import json
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient

from app.archive.api import archive_service
from app.main import app
from tests.integration.test_composite_source_context_custody import context_headers
from tests.integration.test_postgres_document_scope_authorization import _postgres_service


def main() -> None:
    root, evidence = sys.argv[1:]
    cases = json.loads(Path(evidence).read_text())
    assert len(cases) == 11
    app.dependency_overrides[archive_service] = lambda: _postgres_service(Path(root))
    try:
        with TestClient(app) as api:
            for case in cases:
                offer, record = case["offer"], case["record"]
                headers = context_headers(offer)
                route = f"/documents/{record['document_id']}"
                held = api.get(route, headers=headers)
                assert held.status_code == 200 and held.json() == record
                assert record["report_revision_id"] == offer["metadata"]["report_revision_id"]
                assert (
                    record["composite_report_identity"]
                    == offer["metadata"]["composite_report_identity"]
                )
                download = api.get(route + "/download", headers=headers)
                assert download.status_code == 200
                assert download.content == b64decode(offer["content_base64"])
                assert (
                    api.get(route + "/current", headers=headers).json()["document_id"]
                    == case["current_id"]
                )
                assert api.get(route + "/retention", headers=headers).status_code == 200
                events = api.get(route + "/source-events", headers=headers)
                assert events.status_code == 200
                assert (
                    events.json()["events"][0]["report_revision_id"] == record["report_revision_id"]
                )
                assert (
                    events.json()["events"][0]["composite_report_identity"]
                    == record["composite_report_identity"]
                )
                for suffix in ("", "/download", "/current", "/retention", "/source-events"):
                    assert (
                        api.get(
                            route + suffix, headers={**headers, "X-Tenant-Id": "foreign"}
                        ).status_code
                        == 403
                    )
    finally:
        app.dependency_overrides.clear()
    print(json.dumps({"reopened": len(cases), "pid": os.getpid()}))


if __name__ == "__main__":
    main()
