"""Custody refusals surface through the API with both identities named.

The writer-level behaviours are proven in tests/unit/test_archive_custody_verification.py;
these tests hold the HTTP boundary: the 422/409 problem codes render's retry
logic and an operator both depend on (archive#118).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

from fastapi.testclient import TestClient

from app.main import app
from app.archive.api import archive_service
from tests.integration.test_archive_documents_api import (
    _headers,
    _payload,
    _payload_with_id,
    _service,
)

ARTIFACT = b"portfolio review pdf bytes"
ARTIFACT_SHA = hashlib.sha256(ARTIFACT).hexdigest()


def test_false_declaration_is_refused_with_both_hashes_named(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    payload = _payload()
    metadata = cast(dict[str, object], payload["metadata"])
    metadata["document_reference"] = "rdoc_11111111-1111-5111-8111-111111111111"
    metadata["declared_artifact_sha256"] = "0" * 64

    try:
        response = client.post("/documents", json=payload, headers=_headers())

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "declared_checksum_mismatch"
        assert "0" * 64 in error["message"]
        assert ARTIFACT_SHA in error["message"]
        assert not list((tmp_path / "objects").rglob("*"))
    finally:
        app.dependency_overrides.clear()


def test_same_bytes_under_a_second_reference_conflict_with_both_named(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    first = _payload()
    first_metadata = cast(dict[str, object], first["metadata"])
    first_metadata["document_reference"] = "rdoc_11111111-1111-5111-8111-111111111111"
    first_metadata["declared_artifact_sha256"] = ARTIFACT_SHA
    second = _payload_with_id("archive-request-collision-001", ARTIFACT)
    second_metadata = cast(dict[str, object], second["metadata"])
    second_metadata["document_reference"] = "rdoc_22222222-2222-5222-8222-222222222222"
    second_metadata["declared_artifact_sha256"] = ARTIFACT_SHA

    try:
        created = client.post("/documents", json=first, headers=_headers())
        assert created.status_code == 201
        assert created.json()["document_reference"] == ("rdoc_11111111-1111-5111-8111-111111111111")
        assert created.json()["declared_artifact_sha256"] == ARTIFACT_SHA

        collided = client.post("/documents", json=second, headers=_headers())

        assert collided.status_code == 409
        error = collided.json()["error"]
        assert error["code"] == "artifact_identity_collision"
        assert "rdoc_11111111-1111-5111-8111-111111111111" in error["message"]
        assert "rdoc_22222222-2222-5222-8222-222222222222" in error["message"]
    finally:
        app.dependency_overrides.clear()


def test_declared_digest_must_be_a_sha256_hex_digest(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app.dependency_overrides[archive_service] = lambda: service
    client = TestClient(app)
    payload = _payload()
    metadata = cast(dict[str, object], payload["metadata"])
    metadata["declared_artifact_sha256"] = "sha256:not-a-digest"

    try:
        response = client.post("/documents", json=payload, headers=_headers())

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_failed"
        assert not list((tmp_path / "objects").rglob("*"))
    finally:
        app.dependency_overrides.clear()
