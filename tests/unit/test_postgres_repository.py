from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, cast

import pytest
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row

from app.archive.audit import AccessAuditEvent, AccessEventType, AuthorizationDecision
from app.archive.exceptions import DuplicateArchiveRequestConflict
from app.archive.models import (
    ArchiveDocumentMetadata,
    LegalHoldRecord,
    LifecycleTransitionType,
    LifecycleRelationshipRecord,
)
from app.archive.postgres_repository import (
    PostgresAccessAuditRepository,
    PostgresArchiveDocumentRepository,
)
from tests.unit.test_archive_metadata_model import valid_metadata_input


class FakeCursor:
    def __init__(
        self,
        *,
        row: Mapping[str, object] | None = None,
        rows: list[Mapping[str, object]] | None = None,
        error: BaseException | None = None,
        rowcount: int = 1,
    ) -> None:
        self.row = row
        self.rows = rows or []
        self.executions: list[tuple[str, object]] = []
        self.error = error
        self.rowcount = rowcount

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, query: str, parameters: object = None) -> None:
        if self.error is not None:
            raise self.error
        self.executions.append((query, parameters))

    def fetchone(self) -> Mapping[str, object] | None:
        return self.row

    def fetchall(self) -> list[Mapping[str, object]]:
        return self.rows


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self._cursor


class ConnectionSequence:
    def __init__(self, *cursors: FakeCursor) -> None:
        self._cursors = list(cursors)

    def __call__(self) -> FakeConnection:
        return FakeConnection(self._cursors.pop(0))


def _metadata(
    document_id: str = "doc_1", request_id: str = "archive-request-1"
) -> ArchiveDocumentMetadata:
    source = valid_metadata_input(archive_request_id=request_id)
    return ArchiveDocumentMetadata(
        **source.model_dump(),
        document_id=document_id,
        storage_provider="s3",
        storage_namespace="sg-production",
        storage_key=f"sg/tenant/{document_id}.pdf",
        checksum="a" * 64,
        size_bytes=100,
    )


def _row(model: Any) -> Mapping[str, object]:
    return cast(Mapping[str, object], model.model_dump(mode="json"))


def test_postgres_repository_reads_single_and_batch_documents() -> None:
    metadata = _metadata()
    single = FakeCursor(row=_row(metadata))
    batch = FakeCursor(rows=[_row(metadata)])
    repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(single, batch),
    )

    assert repository.get_by_document_id(metadata.document_id) == metadata
    result = repository.get_by_document_ids((metadata.document_id, "missing"))

    assert result.documents == {metadata.document_id: metadata}
    assert "document_id = ANY(%s)" in batch.executions[0][0]
    assert repository.get_by_document_ids(()).documents == {}


def test_postgres_repositories_measure_required_schema_readiness() -> None:
    document_cursor = FakeCursor()
    audit_cursor = FakeCursor()
    document_repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(document_cursor),
    )
    audit_repository = PostgresAccessAuditRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(audit_cursor),
    )

    document_repository.check_ready()
    audit_repository.check_ready()

    assert document_cursor.executions == [("SELECT 1 FROM archive_documents LIMIT 1", None)]
    assert audit_cursor.executions == [("SELECT 1 FROM archive_access_audit LIMIT 1", None)]


def test_postgres_repository_requires_dsn_and_uses_default_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        PostgresArchiveDocumentRepository(" ")

    cursor = FakeCursor(row=None)
    captured: dict[str, object] = {}

    def connect(dsn: str, **kwargs: object) -> FakeConnection:
        captured.update({"dsn": dsn, **kwargs})
        return FakeConnection(cursor)

    monkeypatch.setattr("app.archive.postgres_repository.psycopg.connect", connect)
    repository = PostgresArchiveDocumentRepository("postgresql://archive/test")

    assert repository.get_by_document_id("missing") is None
    assert captured["dsn"] == "postgresql://archive/test"
    assert captured["row_factory"] is dict_row


def test_postgres_repository_saves_document_with_idempotency_preflight() -> None:
    metadata = _metadata()
    lookup = FakeCursor(row=None)
    save = FakeCursor()
    repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(lookup, save),
    )

    assert repository.save(metadata) == metadata

    assert "archive_request_id = %s" in lookup.executions[0][0]
    assert "ON CONFLICT (document_id) DO UPDATE" in save.executions[0][0]


def test_postgres_repository_rejects_request_id_owned_by_another_document() -> None:
    existing = _metadata(document_id="doc_existing")
    repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(FakeCursor(row=_row(existing))),
    )

    with pytest.raises(DuplicateArchiveRequestConflict):
        repository.save(_metadata(document_id="doc_new"))


def test_postgres_repository_maps_unique_constraint_race_to_domain_conflict() -> None:
    repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(
            FakeCursor(row=None),
            FakeCursor(error=UniqueViolation("duplicate key")),
        ),
    )

    with pytest.raises(DuplicateArchiveRequestConflict, match="storage key"):
        repository.save(_metadata())


def test_postgres_repository_persists_legal_hold_and_lifecycle_records() -> None:
    hold = LegalHoldRecord(
        legal_hold_id="hold_1",
        document_id="doc_1",
        hold_reason="Regulatory inquiry",
        authority_reference="AUTH-1",
        requested_by="operations-user",
    )
    relationship = LifecycleRelationshipRecord(
        lifecycle_relationship_id="lifecycle_1",
        source_document_id="doc_1",
        target_document_id="doc_2",
        transition_type=LifecycleTransitionType.SUPERSEDE,
        transition_reason="Quarter-end correction",
        transition_reason_code="archive_document_supersession_requested",
        requested_by="operations-user",
    )
    save_hold = FakeCursor()
    get_hold = FakeCursor(row=_row(hold))
    list_holds = FakeCursor(rows=[_row(hold)])
    save_relationship = FakeCursor()
    list_relationships = FakeCursor(rows=[_row(relationship)])
    delete_relationship = FakeCursor()
    repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(
            save_hold,
            get_hold,
            list_holds,
            save_relationship,
            list_relationships,
            delete_relationship,
        ),
    )

    assert repository.save_legal_hold(hold) == hold
    assert repository.get_legal_hold(hold.legal_hold_id) == hold
    assert repository.list_legal_holds(hold.document_id) == [hold]
    assert repository.save_lifecycle_relationship(relationship) == relationship
    assert repository.list_lifecycle_relationships("doc_1") == [relationship]
    repository.delete_lifecycle_relationship(relationship.lifecycle_relationship_id)

    assert "INSERT INTO archive_legal_holds" in save_hold.executions[0][0]
    assert "INSERT INTO archive_lifecycle_relationships" in save_relationship.executions[0][0]
    assert "DELETE FROM archive_lifecycle_relationships" in delete_relationship.executions[0][0]


def test_postgres_access_audit_repository_persists_and_lists_events() -> None:
    event = AccessAuditEvent(
        audit_event_id="audit_1",
        document_id="doc_1",
        event_type=AccessEventType.METADATA_READ,
        actor_type="service",
        actor_id="gateway",
        caller_service="lotus-gateway",
        authorization_decision=AuthorizationDecision.ALLOWED,
        authorization_reason_code="archive_read_allowed",
        correlation_id="corr-1",
        trace_id="trace-1",
        created_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )
    record = FakeCursor()
    listing = FakeCursor(rows=[_row(event)])
    repository = PostgresAccessAuditRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(record, listing),
    )

    assert repository.record(event) == event
    assert repository.list_by_document_id("doc_1") == [event]

    assert "INSERT INTO archive_access_audit" in record.executions[0][0]
    assert "IS NOT DISTINCT FROM %s" in listing.executions[0][0]


def test_save_sql_updates_only_mutable_columns_and_guards_every_immutable_one() -> None:
    """The upsert must not be able to rewrite history, column by column."""
    from app.archive.models import MUTABLE_DOCUMENT_FIELDS
    from app.archive.postgres_repository import _DOCUMENT_COLUMNS, _SAVE_DOCUMENT_SQL

    set_clause = _SAVE_DOCUMENT_SQL.split("DO UPDATE SET ", 1)[1].split(" WHERE ", 1)[0]
    updated = {part.split(" = ")[0].strip() for part in set_clause.split(", ")}
    assert updated == MUTABLE_DOCUMENT_FIELDS, (
        "the ON CONFLICT update must set exactly the registered mutable fields; "
        f"unexpected={sorted(updated - MUTABLE_DOCUMENT_FIELDS)} "
        f"missing={sorted(MUTABLE_DOCUMENT_FIELDS - updated)}"
    )

    guard_clause = _SAVE_DOCUMENT_SQL.split(" WHERE ", 1)[1]
    immutable = [
        column
        for column in _DOCUMENT_COLUMNS
        if column != "document_id" and column not in MUTABLE_DOCUMENT_FIELDS
    ]
    for column in immutable:
        assert f"archive_documents.{column} IS NOT DISTINCT FROM EXCLUDED.{column}" in (
            guard_clause
        ), f"immutable column {column} is not guarded"


def test_save_raises_historical_integrity_error_when_the_guard_blocks_the_update() -> None:
    """rowcount 0 on the guarded upsert means an immutable field differed."""
    from app.archive.exceptions import HistoricalIntegrityError

    lookup_cursor = FakeCursor(row=None)
    write_cursor = FakeCursor(rowcount=0)
    repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(lookup_cursor, write_cursor),
    )

    with pytest.raises(HistoricalIntegrityError):
        repository.save(_metadata())

    assert write_cursor.executions, "the guarded upsert must have been attempted"


def test_save_succeeds_when_the_guarded_upsert_updates_a_row() -> None:
    lookup_cursor = FakeCursor(row=None)
    write_cursor = FakeCursor(rowcount=1)
    repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(lookup_cursor, write_cursor),
    )

    saved = repository.save(_metadata())

    assert saved.document_id == "doc_1"
