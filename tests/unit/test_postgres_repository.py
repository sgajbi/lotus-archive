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
    LegalHoldStatus,
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
        fetchone_queue: list[Mapping[str, object] | None] | None = None,
        error: BaseException | None = None,
        rowcount: int = 1,
    ) -> None:
        self.row = row
        self.rows = rows or []
        self.fetchone_queue = fetchone_queue
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
        if self.fetchone_queue is not None:
            return self.fetchone_queue.pop(0) if self.fetchone_queue else None
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


def test_postgres_repository_finds_custody_holders_by_checksum() -> None:
    """The collision check asks "who already holds these exact bytes" - the
    lookup must go to SQL by checksum and validate what comes back."""
    metadata = _metadata()
    by_checksum = FakeCursor(rows=[_row(metadata)])
    empty = FakeCursor(rows=[])
    repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(by_checksum, empty),
    )

    held = repository.get_by_checksum(metadata.checksum)

    assert held == [metadata]
    assert "WHERE checksum = %s" in by_checksum.executions[0][0]
    assert by_checksum.executions[0][1] == (metadata.checksum,)
    assert repository.get_by_checksum("f" * 64) == []


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
    get_hold = FakeCursor(row=_row(hold))
    list_holds = FakeCursor(rows=[_row(hold)])
    list_relationships = FakeCursor(rows=[_row(relationship)])
    repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(
            get_hold,
            list_holds,
            list_relationships,
        ),
    )

    assert repository.get_legal_hold(hold.legal_hold_id) == hold
    assert repository.list_legal_holds(hold.document_id) == [hold]
    assert repository.list_lifecycle_relationships("doc_1") == [relationship]

    assert "FROM archive_legal_holds" in get_hold.executions[0][0]
    assert "ORDER BY requested_at" in list_holds.executions[0][0]
    assert "FROM archive_lifecycle_relationships" in list_relationships.executions[0][0]


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


def test_save_sql_updates_only_updated_at_and_guards_every_other_column() -> None:
    """save() may write ONLY `updated_at` on an existing row (issue #166).

    Retention, hold and lifecycle columns move exclusively through their owning
    transitions, so the ON CONFLICT update must not be ABLE to carry a caller
    snapshot into any of them - and every other column, immutable identity and
    transition-owned posture alike, must be guarded for equality.
    """
    from app.archive.postgres_repository import _DOCUMENT_COLUMNS, _SAVE_DOCUMENT_SQL

    set_clause = _SAVE_DOCUMENT_SQL.split("DO UPDATE SET ", 1)[1].split(" WHERE ", 1)[0]
    updated = {part.split(" = ")[0].strip() for part in set_clause.split(", ")}
    assert updated == {"updated_at"}, (
        "the ON CONFLICT update must set exactly updated_at; "
        f"unexpected={sorted(updated - {'updated_at'})}"
    )

    guard_clause = _SAVE_DOCUMENT_SQL.split(" WHERE ", 1)[1]
    guarded = [
        column
        for column in _DOCUMENT_COLUMNS
        if column not in {"document_id", "updated_at"}
    ]
    for column in guarded:
        assert f"archive_documents.{column} IS NOT DISTINCT FROM EXCLUDED.{column}" in (
            guard_clause
        ), f"column {column} is not guarded against save() rewrite"


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


def test_connection_factory_bounds_connect_and_statement_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure containment: a hung PostgreSQL must fail the request, never hold it."""
    import psycopg

    from app.archive.postgres_repository import _connection_factory

    captured: dict[str, object] = {}

    def fake_connect(dsn: str, **kwargs: object) -> object:
        captured["dsn"] = dsn
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    factory = _connection_factory(
        "postgresql://example",
        connect_timeout_seconds=7,
        statement_timeout_ms=1234,
    )
    factory()

    assert captured["connect_timeout"] == 7
    assert captured["options"] == "-c statement_timeout=1234"


def test_audit_listing_pages_in_sql_not_in_python() -> None:
    """The audit table grows for the life of a document; one page must not load every row."""
    cursor = FakeCursor(rows=[])
    repository = PostgresAccessAuditRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(cursor),
    )

    repository.list_by_document_id("doc_1", limit=25, offset=50)

    query, parameters = cursor.executions[0]
    assert "LIMIT %s OFFSET %s" in query
    assert parameters == ("doc_1", 25, 50)


def test_audit_count_uses_a_count_query() -> None:
    cursor = FakeCursor(row={"total": 7})
    repository = PostgresAccessAuditRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(cursor),
    )

    assert repository.count_by_document_id("doc_1") == 7
    query, _ = cursor.executions[0]
    assert "count(*)" in query


def test_pooled_connection_factory_configures_and_opens_the_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pool must carry the #106 bounds, open in the background, and hand back its close."""
    import app.archive.postgres_repository as module

    captured: dict[str, object] = {}

    class FakePool:
        def __init__(self, conninfo: str, **kwargs: object) -> None:
            captured["conninfo"] = conninfo
            captured.update(kwargs)
            self.opened_wait: bool | None = None

        def open(self, wait: bool = True) -> None:
            self.opened_wait = wait
            captured["opened"] = True

        def connection(self) -> object:  # pragma: no cover - identity only
            return object()

        def close(self) -> None:  # pragma: no cover - identity only
            return None

    monkeypatch.setattr(module, "ConnectionPool", FakePool)
    factory, close = module.pooled_connection_factory(
        "postgresql://example",
        connect_timeout_seconds=4,
        statement_timeout_ms=2500,
        min_size=2,
        max_size=6,
    )

    assert captured["opened"] is True
    assert captured["min_size"] == 2
    assert captured["max_size"] == 6
    assert captured["open"] is False
    assert captured["timeout"] == 4.0
    kwargs = captured["kwargs"]
    assert kwargs["connect_timeout"] == 4  # type: ignore[index]
    assert kwargs["options"] == "-c statement_timeout=2500"  # type: ignore[index]
    assert callable(factory) and callable(close)


def _lifecycle_relationship(relationship_id: str = "life_1") -> LifecycleRelationshipRecord:
    return LifecycleRelationshipRecord(
        lifecycle_relationship_id=relationship_id,
        source_document_id="doc_source",
        target_document_id="doc_target",
        transition_type=LifecycleTransitionType.SUPERSEDE,
        transition_reason="Approved replacement",
        transition_reason_code="document_superseded_by_newer_version",
        requested_by="ops-user",
    )


def test_lifecycle_transition_locks_both_rows_then_writes_only_decided_columns() -> None:
    """One connection: two sorted FOR UPDATE locks, two column-scoped updates,
    one relationship insert. No whole-snapshot upsert can appear here - that
    shape is what reverted committed purge and hold state (issue #166)."""
    source = _metadata("doc_source", "req-source")
    target = _metadata("doc_target", "req-target")
    source_after = source.model_copy(update={"superseded_by_document_id": "doc_target"})
    target_after = target.model_copy(update={"supersedes_document_id": "doc_source"})
    cursor = FakeCursor(
        fetchone_queue=[_row(source), _row(target), _row(source_after), _row(target_after)],
    )
    repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(cursor),
    )

    relationship, updated_source, updated_target = repository.apply_lifecycle_transition(
        source_document_id="doc_source",
        target_document_id="doc_target",
        transition_type=LifecycleTransitionType.SUPERSEDE,
        relationship=_lifecycle_relationship(),
    )

    queries = [query for query, _ in cursor.executions]
    assert len(queries) == 5, "exactly five statements, one connection"
    assert "FOR UPDATE" in queries[0] and cursor.executions[0][1] == ("doc_source",)
    assert "FOR UPDATE" in queries[1] and cursor.executions[1][1] == ("doc_target",)
    assert "SET superseded_by_document_id = %s, updated_at = %s" in queries[2]
    assert "SET supersedes_document_id = %s, updated_at = %s" in queries[3]
    assert "INSERT INTO archive_lifecycle_relationships" in queries[4]
    for query in queries:
        assert "ON CONFLICT (document_id)" not in query, (
            "the transition must never route a document snapshot through the save upsert"
        )
    assert relationship.lifecycle_relationship_id == "life_1"
    assert updated_source.superseded_by_document_id == "doc_target"
    assert updated_target.supersedes_document_id == "doc_source"


def test_lifecycle_transition_refuses_on_the_locked_rows_before_any_write() -> None:
    """The stored state decides: a purged target read UNDER THE LOCK refuses the
    transition, and no mutating statement runs after the refusal."""
    from app.archive.exceptions import UnsupportedLifecycleTransitionError
    from app.archive.models import PurgeStatus

    source = _metadata("doc_source", "req-source")
    purged_target = _metadata("doc_target", "req-target").model_copy(
        update={
            "purge_status": PurgeStatus.PURGED,
            "purge_started_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
            "purged_at": datetime(2026, 9, 1, 1, tzinfo=timezone.utc),
        }
    )
    cursor = FakeCursor(fetchone_queue=[_row(source), _row(purged_target)])
    repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(cursor),
    )

    with pytest.raises(UnsupportedLifecycleTransitionError):
        repository.apply_lifecycle_transition(
            source_document_id="doc_source",
            target_document_id="doc_target",
            transition_type=LifecycleTransitionType.SUPERSEDE,
            relationship=_lifecycle_relationship("life_refused"),
        )

    queries = [query for query, _ in cursor.executions]
    assert len(queries) == 2, "the refusal must precede every write"
    assert all("FOR UPDATE" in query for query in queries)


def test_refresh_summary_locks_the_document_then_derives_in_sql() -> None:
    """The recount is DERIVED in the statement, under the lock taken first;
    no caller-computed status or count parameter exists to be stale."""
    metadata = _metadata()
    cursor = FakeCursor(fetchone_queue=[_row(metadata), _row(metadata)])
    repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(cursor),
    )

    refreshed = repository.refresh_legal_hold_summary(metadata.document_id)

    assert refreshed == metadata
    lock_query, lock_params = cursor.executions[0]
    assert "FOR UPDATE" in lock_query and lock_params == (metadata.document_id,)
    refresh_query, refresh_params = cursor.executions[1]
    assert "hold_status = 'active'" in refresh_query
    assert "count(*)" in refresh_query
    assert "legal_hold_status IS DISTINCT FROM" in refresh_query
    assert not any(
        isinstance(parameter, (int, LegalHoldStatus)) for parameter in refresh_params  # type: ignore[union-attr]
    ), "no caller-computed status or count may reach the summary write"


def test_release_and_record_legal_hold_is_one_transaction() -> None:
    """Document lock first, conditional hold release, derived recount - one
    connection, mirroring the admission boundary."""
    hold = LegalHoldRecord(
        legal_hold_id="hold_1",
        document_id="doc_1",
        hold_reason="Regulatory inquiry",
        authority_reference="AUTH-1",
        requested_by="operations-user",
    )
    metadata = _metadata()
    cursor = FakeCursor(
        fetchone_queue=[{"document_id": "doc_1"}, _row(hold), _row(metadata)],
    )
    repository = PostgresArchiveDocumentRepository(
        "postgresql://unused",
        connection_factory=ConnectionSequence(cursor),
    )

    released = repository.release_and_record_legal_hold(
        document_id="doc_1",
        legal_hold_id="hold_1",
        released_by="compliance-officer",
        released_at=datetime(2026, 9, 13, tzinfo=timezone.utc),
        release_reason="matter closed",
    )

    assert released is not None
    queries = [query for query, _ in cursor.executions]
    assert len(queries) == 3, "lock, conditional release, derived recount - one connection"
    assert "FOR UPDATE" in queries[0]
    assert "hold_status = 'active'" in queries[1] and "SET hold_status = 'clear'" in queries[1]
    assert "legal_hold_status IS DISTINCT FROM" in queries[2]
