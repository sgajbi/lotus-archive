from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.archive.audit import AccessAuditEvent
from app.archive.exceptions import DuplicateArchiveRequestConflict, HistoricalIntegrityError
from app.archive.models import (
    MUTABLE_DOCUMENT_FIELDS,
    ArchiveDocumentMetadata,
    LegalHoldRecord,
    LifecycleRelationshipRecord,
)
from app.archive.repository import ArchiveDocumentBatchLookup

ConnectionFactory = Callable[[], Any]

_DOCUMENT_COLUMNS = tuple(ArchiveDocumentMetadata.model_fields)
_DOCUMENT_JSON_COLUMNS = frozenset(
    {"reviewed_advisory_narrative", "advisor_proposal_memo", "idea_evidence_pack"}
)
_LEGAL_HOLD_COLUMNS = tuple(LegalHoldRecord.model_fields)
_LIFECYCLE_COLUMNS = tuple(LifecycleRelationshipRecord.model_fields)
_AUDIT_COLUMNS = tuple(AccessAuditEvent.model_fields)


def _insert_sql(
    table: str,
    columns: tuple[str, ...],
    *,
    conflict_key: str,
    mutable_columns: frozenset[str] | None = None,
) -> str:
    updatable = tuple(
        column
        for column in columns
        if column != conflict_key and (mutable_columns is None or column in mutable_columns)
    )
    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in updatable)
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"VALUES ({', '.join(['%s'] * len(columns))}) "
        f"ON CONFLICT ({conflict_key}) DO UPDATE SET {assignments}"
    )
    if mutable_columns is not None:
        # The update applies only when every immutable column is unchanged. A conflicting write
        # that tries to move identity, provenance, content identity or tenant scope resolves the
        # conflict by updating nothing, which save() detects via rowcount and raises
        # HistoricalIntegrityError - race-safe in a single round trip.
        guards = " AND ".join(
            f"{table}.{column} IS NOT DISTINCT FROM EXCLUDED.{column}"
            for column in columns
            if column != conflict_key and column not in mutable_columns
        )
        sql += f" WHERE {guards}"
    return sql


_SAVE_DOCUMENT_SQL = _insert_sql(
    "archive_documents",
    _DOCUMENT_COLUMNS,
    conflict_key="document_id",
    mutable_columns=MUTABLE_DOCUMENT_FIELDS,
)
_SAVE_LEGAL_HOLD_SQL = _insert_sql(
    "archive_legal_holds", _LEGAL_HOLD_COLUMNS, conflict_key="legal_hold_id"
)
_SAVE_LIFECYCLE_SQL = _insert_sql(
    "archive_lifecycle_relationships",
    _LIFECYCLE_COLUMNS,
    conflict_key="lifecycle_relationship_id",
)
_RECORD_AUDIT_SQL = (
    f"INSERT INTO archive_access_audit ({', '.join(_AUDIT_COLUMNS)}) "
    f"VALUES ({', '.join(['%s'] * len(_AUDIT_COLUMNS))})"
)


DEFAULT_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_STATEMENT_TIMEOUT_MS = 30_000


def _connection_factory(
    dsn: str,
    *,
    connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
) -> ConnectionFactory:
    """Every connection is bounded: a hung PostgreSQL fails the request, never holds it."""
    if not dsn.strip():
        raise ValueError("PostgreSQL DSN must not be blank")

    def connect() -> Any:
        return psycopg.connect(
            dsn,
            row_factory=dict_row,
            connect_timeout=connect_timeout_seconds,
            options=f"-c statement_timeout={statement_timeout_ms}",
        )

    return connect


def _values(model: Any, columns: tuple[str, ...]) -> tuple[object, ...]:
    data = model.model_dump()
    return tuple(data[column] for column in columns)


def _document_values(metadata: ArchiveDocumentMetadata) -> tuple[object, ...]:
    data = metadata.model_dump()
    return tuple(
        Jsonb(data[column])
        if column in _DOCUMENT_JSON_COLUMNS and data[column] is not None
        else data[column]
        for column in _DOCUMENT_COLUMNS
    )


class PostgresArchiveDocumentRepository:
    def __init__(
        self,
        dsn: str,
        *,
        connection_factory: ConnectionFactory | None = None,
        connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    ) -> None:
        self._connect = connection_factory or _connection_factory(
            dsn,
            connect_timeout_seconds=connect_timeout_seconds,
            statement_timeout_ms=statement_timeout_ms,
        )

    def check_ready(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM archive_documents LIMIT 1")

    def get_by_document_id(self, document_id: str) -> ArchiveDocumentMetadata | None:
        return self._fetch_document("document_id = %s", (document_id,))

    def get_by_document_ids(
        self,
        document_ids: tuple[str, ...],
    ) -> ArchiveDocumentBatchLookup:
        if not document_ids:
            return ArchiveDocumentBatchLookup(documents={})
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM archive_documents WHERE document_id = ANY(%s)",
                (list(document_ids),),
            )
            documents = {
                metadata.document_id: metadata
                for metadata in (
                    ArchiveDocumentMetadata.model_validate(row) for row in cursor.fetchall()
                )
            }
        return ArchiveDocumentBatchLookup(documents=documents)

    def get_by_archive_request_id(
        self,
        archive_request_id: str,
    ) -> ArchiveDocumentMetadata | None:
        return self._fetch_document("archive_request_id = %s", (archive_request_id,))

    def save(self, metadata: ArchiveDocumentMetadata) -> ArchiveDocumentMetadata:
        existing = self.get_by_archive_request_id(metadata.archive_request_id)
        if existing is not None and existing.document_id != metadata.document_id:
            raise DuplicateArchiveRequestConflict(
                "archive_request_id already belongs to another document"
            )
        try:
            with self._connect() as connection, connection.cursor() as cursor:
                cursor.execute(_SAVE_DOCUMENT_SQL, _document_values(metadata))
                if cursor.rowcount == 0:
                    raise HistoricalIntegrityError(
                        "immutable document fields cannot change after archival"
                    )
        except UniqueViolation as exc:
            raise DuplicateArchiveRequestConflict(
                "archive request or storage key already belongs to another document"
            ) from exc
        return metadata

    def save_legal_hold(self, legal_hold: LegalHoldRecord) -> LegalHoldRecord:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(_SAVE_LEGAL_HOLD_SQL, _values(legal_hold, _LEGAL_HOLD_COLUMNS))
        return legal_hold

    def get_legal_hold(self, legal_hold_id: str) -> LegalHoldRecord | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM archive_legal_holds WHERE legal_hold_id = %s",
                (legal_hold_id,),
            )
            row = cursor.fetchone()
        return LegalHoldRecord.model_validate(row) if row is not None else None

    def list_legal_holds(self, document_id: str) -> list[LegalHoldRecord]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM archive_legal_holds WHERE document_id = %s ORDER BY requested_at",
                (document_id,),
            )
            rows = cursor.fetchall()
        return [LegalHoldRecord.model_validate(row) for row in rows]

    def save_lifecycle_relationship(
        self,
        relationship: LifecycleRelationshipRecord,
    ) -> LifecycleRelationshipRecord:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                _SAVE_LIFECYCLE_SQL,
                _values(relationship, _LIFECYCLE_COLUMNS),
            )
        return relationship

    def delete_lifecycle_relationship(self, lifecycle_relationship_id: str) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM archive_lifecycle_relationships WHERE lifecycle_relationship_id = %s",
                (lifecycle_relationship_id,),
            )

    def list_lifecycle_relationships(
        self,
        document_id: str,
    ) -> list[LifecycleRelationshipRecord]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM archive_lifecycle_relationships "
                "WHERE source_document_id = %s OR target_document_id = %s "
                "ORDER BY requested_at",
                (document_id, document_id),
            )
            rows = cursor.fetchall()
        return [LifecycleRelationshipRecord.model_validate(row) for row in rows]

    def _fetch_document(
        self,
        predicate: str,
        parameters: tuple[object, ...],
    ) -> ArchiveDocumentMetadata | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM archive_documents WHERE {predicate}", parameters)
            row: Mapping[str, object] | None = cursor.fetchone()
        return ArchiveDocumentMetadata.model_validate(row) if row is not None else None


class PostgresAccessAuditRepository:
    def __init__(
        self,
        dsn: str,
        *,
        connection_factory: ConnectionFactory | None = None,
        connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
        statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    ) -> None:
        self._connect = connection_factory or _connection_factory(
            dsn,
            connect_timeout_seconds=connect_timeout_seconds,
            statement_timeout_ms=statement_timeout_ms,
        )

    def check_ready(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM archive_access_audit LIMIT 1")

    def record(self, event: AccessAuditEvent) -> AccessAuditEvent:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(_RECORD_AUDIT_SQL, _values(event, _AUDIT_COLUMNS))
        return event

    def list_by_document_id(
        self,
        document_id: str | None,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[AccessAuditEvent]:
        """Page in SQL: the audit table grows for the life of a document, so reads must not
        load every event to serve one page."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM archive_access_audit "
                "WHERE document_id IS NOT DISTINCT FROM %s "
                "ORDER BY created_at, audit_event_id "
                "LIMIT %s OFFSET %s",
                (document_id, limit, offset),
            )
            rows = cursor.fetchall()
        return [AccessAuditEvent.model_validate(row) for row in rows]

    def count_by_document_id(self, document_id: str | None) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) AS total FROM archive_access_audit "
                "WHERE document_id IS NOT DISTINCT FROM %s",
                (document_id,),
            )
            row = cursor.fetchone()
        return int(row["total"]) if row is not None else 0
