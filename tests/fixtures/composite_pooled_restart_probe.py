"""Fresh-process reads of the populated v5 custody upgrade, never a DR claim."""

import json
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient

from app.archive.api import archive_service
from app.main import app
from tests.integration.test_composite_pooled_custody import assert_pooled_reads, pooled_headers
from tests.integration.test_postgres_document_scope_authorization import _postgres_service


def main() -> None:
    root, evidence = sys.argv[1:]
    cases = json.loads(Path(evidence).read_text())
    assert len(cases) == 8
    service = _postgres_service(Path(root))
    app.dependency_overrides[archive_service] = lambda: service
    try:
        with TestClient(app) as api:
            for case, record in cases:
                assert_pooled_reads(api, record, case)
                expected = cases[2][1] if case in {"original", "technical"} else record
                assert (
                    api.get(
                        f"/documents/{record['document_id']}/current", headers=pooled_headers()
                    ).json()["document_id"]
                    == expected["document_id"]
                )
    finally:
        app.dependency_overrides.clear()
    print(json.dumps({"reopened": 8, "pid": os.getpid()}))


if __name__ == "__main__":
    main()
