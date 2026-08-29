from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path

import psycopg
import pytest

from app.archive.audit import AccessAuditEvent, AccessEventType, AuthorizationDecision
from app.archive.models import ArchiveDocumentMetadata
from app.archive.postgres_repository import (
    PostgresAccessAuditRepository,
    PostgresArchiveDocumentRepository,
)
from tests.unit.test_archive_metadata_model import valid_metadata_input

ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("LOTUS_ARCHIVE_TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="LOTUS_ARCHIVE_TEST_DATABASE_URL is required for PostgreSQL adapter proof",
)


@pytest.fixture(autouse=True)
def migrated_database() -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            connection.execute(migration.read_text(encoding="utf-8"))
        connection.execute("TRUNCATE archive_access_audit")
        connection.execute(
            "TRUNCATE archive_lifecycle_relationships, archive_legal_holds, archive_documents"
        )


def _metadata() -> ArchiveDocumentMetadata:
    source = valid_metadata_input()
    return ArchiveDocumentMetadata(
        **source.model_dump(),
        document_id="doc_postgres_restart_proof",
        storage_provider="s3",
        storage_namespace="sg-production",
        storage_key="sg/tenant/doc_postgres_restart_proof.pdf",
        checksum="a" * 64,
        size_bytes=100,
    )


def test_postgres_metadata_and_audit_survive_repository_reconstruction() -> None:
    metadata = _metadata()
    writer_repository = PostgresArchiveDocumentRepository(DATABASE_URL)
    writer_repository.save(metadata)

    event = AccessAuditEvent(
        audit_event_id="audit_postgres_restart_proof",
        document_id=metadata.document_id,
        event_type=AccessEventType.ARCHIVE_CREATE,
        actor_type="service",
        actor_id="lotus-report",
        caller_service="lotus-report",
        authorization_decision=AuthorizationDecision.ALLOWED,
        authorization_reason_code="archive_create_allowed",
        correlation_id="corr-postgres-proof",
        trace_id="trace-postgres-proof",
        created_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )
    PostgresAccessAuditRepository(DATABASE_URL).record(event)

    restarted_repository = PostgresArchiveDocumentRepository(DATABASE_URL)
    restarted_audit = PostgresAccessAuditRepository(DATABASE_URL)

    assert restarted_repository.get_by_document_id(metadata.document_id) == metadata
    assert restarted_audit.list_by_document_id(metadata.document_id) == [event]
