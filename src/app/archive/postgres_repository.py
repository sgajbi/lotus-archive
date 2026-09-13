from __future__ import annotations

from datetime import datetime, timezone

from collections.abc import Callable, Mapping
from typing import Any

import psycopg
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from psycopg.types.json import Jsonb

from app.archive.audit import AccessAuditEvent
from app.archive.exceptions import (
    DocumentNotFoundError,
    DuplicateArchiveRequestConflict,
    HistoricalIntegrityError,
    SupersessionConflictError,
    UnsupportedLifecycleTransitionError,
)
from app.archive.lifecycle_transitions import (
    transition_pointers_agree,
    validate_lifecycle_preconditions,
)
from app.archive.models import (
    LIFECYCLE_TARGET_ORIGIN_FIELD,
    ArchiveDocumentMetadata,
    LegalHoldRecord,
    LifecycleRelationshipRecord,
    LifecycleTransitionType,
)
from app.archive.repository import ArchiveDocumentBatchLookup

ConnectionFactory = Callable[[], Any]

_DOCUMENT_COLUMNS = tuple(ArchiveDocumentMetadata.model_fields)
_DOCUMENT_JSON_COLUMNS = frozenset(
    {
        "reviewed_advisory_narrative",
        "advisor_proposal_memo",
        "advisor_commentary",
        "idea_evidence_pack",
    }
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


# save() may write ONLY `updated_at` on an existing row. Retention, hold and
# lifecycle columns move exclusively through their owning transitions
# (`begin_purge`, `admit_and_record_legal_hold`, `refresh_legal_hold_summary`,
# `apply_lifecycle_transition`, ...), so a caller snapshot handed to save()
# cannot revert state another writer committed since the snapshot was read
# (issue #166). Every other column difference resolves the conflict by updating
# nothing, which save() reports as HistoricalIntegrityError.
_SAVE_DOCUMENT_SQL = _insert_sql(
    "archive_documents",
    _DOCUMENT_COLUMNS,
    conflict_key="document_id",
    mutable_columns=frozenset({"updated_at"}),
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

# The summary is DERIVED from the hold rows in the same statement that writes
# it - the repository never accepts a caller-computed status or count (issue
# #166). Runs only after this transaction holds the document row lock: every
# hold writer takes that lock first, so once it is granted the recount's
# snapshot includes every committed hold write, and later writers wait until
# this transaction commits. The change predicate keeps an unchanged summary
# from churning `updated_at`. Parameters: (updated_at, document_id, document_id).
_REFRESH_HOLD_SUMMARY_SQL = """
    UPDATE archive_documents AS d
    SET legal_hold_status = h.derived_status,
        legal_hold_count = h.derived_count,
        updated_at = %s
    FROM (
        SELECT
            CASE WHEN count(*) > 0 THEN 'active' ELSE 'clear' END AS derived_status,
            count(*)::int AS derived_count
        FROM archive_legal_holds
        WHERE document_id = %s AND hold_status = 'active'
    ) AS h
    WHERE d.document_id = %s
      AND (d.legal_hold_status IS DISTINCT FROM h.derived_status
           OR d.legal_hold_count IS DISTINCT FROM h.derived_count)
    RETURNING d.*
"""

# One statement per transition type, generated from the code-owned column
# mapping so no request value ever reaches SQL text. Parameters:
# (source_document_id, updated_at, target_document_id).
_TARGET_ORIGIN_UPDATE_SQL: dict[LifecycleTransitionType, str] = {
    transition: (
        f"UPDATE archive_documents SET {origin_field} = %s, updated_at = %s "
        "WHERE document_id = %s RETURNING *"
    )
    for transition, origin_field in LIFECYCLE_TARGET_ORIGIN_FIELD.items()
}


DEFAULT_POOL_MIN_SIZE = 1
DEFAULT_POOL_MAX_SIZE = 10
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


def pooled_connection_factory(
    dsn: str,
    *,
    connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    statement_timeout_ms: int = DEFAULT_STATEMENT_TIMEOUT_MS,
    min_size: int = DEFAULT_POOL_MIN_SIZE,
    max_size: int = DEFAULT_POOL_MAX_SIZE,
) -> tuple[ConnectionFactory, Callable[[], None]]:
    """One pool per DSN, shared by every repository built on it (issue #107).

    Returns the connection factory plus the pool's close - the caller owns shutdown. The pool
    opens in the background (open(wait=False)), so composition never blocks on an unreachable
    database; the first connection() waits up to the checkout timeout and then fails, which
    readiness reports honestly. Timeouts from #106 ride along on every pooled connection.
    """
    if not dsn.strip():
        raise ValueError("PostgreSQL DSN must not be blank")
    pool = ConnectionPool(
        dsn,
        min_size=min_size,
        max_size=max_size,
        open=False,
        timeout=float(connect_timeout_seconds),
        kwargs={
            "row_factory": dict_row,
            "connect_timeout": connect_timeout_seconds,
            "options": f"-c statement_timeout={statement_timeout_ms}",
        },
    )
    pool.open(wait=False)
    return pool.connection, pool.close


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

    def get_by_checksum(self, checksum: str) -> list[ArchiveDocumentMetadata]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM archive_documents WHERE checksum = %s",
                (checksum,),
            )
            rows = cursor.fetchall()
        return [ArchiveDocumentMetadata.model_validate(row) for row in rows]

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

    def begin_purge(
        self,
        *,
        document_id: str,
        started_at: datetime,
    ) -> ArchiveDocumentMetadata | None:
        """Conditional acquire of the destruction intent. One statement, one decision.

        `WHERE purge_started_at IS NULL AND legal_hold_status <> 'active'` is the
        mutual exclusion: a hold admitted by any worker or replica has already
        written `active` to this row, so the update matches nothing and the
        purge is refused. A process-local lock could not do this -- the deployed
        shape is multiple workers against one database.

        An already-claimed intent returns the current row rather than None, so a
        retry of an interrupted purge is idempotent rather than refused.

        The NOT EXISTS belt consults the hold ROWS as well as the summary. It is
        not the concurrency mechanism - a blocked UPDATE re-checks only the
        locked row's columns against the new version, not subqueries on other
        tables - the summary column carries the race. The belt refuses
        destruction for LEGACY rows whose summary drifted before recounts became
        derived-in-transaction (issue #166): an active hold row must veto
        destruction even when a historic race left the summary saying clear.
        """
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE archive_documents
                SET purge_started_at = %s, updated_at = %s
                WHERE document_id = %s
                  AND purge_started_at IS NULL
                  AND legal_hold_status <> 'active'
                  AND NOT EXISTS (
                      SELECT 1 FROM archive_legal_holds
                      WHERE document_id = %s AND hold_status = 'active'
                  )
                RETURNING *
                """,
                (started_at, started_at, document_id, document_id),
            )
            row = cursor.fetchone()
            if row is not None:
                return ArchiveDocumentMetadata.model_validate(row)
            # No row updated: either the intent is already held (idempotent
            # retry) or a hold owns the document (refusal). Distinguish them.
            cursor.execute(
                "SELECT * FROM archive_documents WHERE document_id = %s",
                (document_id,),
            )
            current = cursor.fetchone()
        if current is None:
            return None
        metadata = ArchiveDocumentMetadata.model_validate(current)
        return metadata if metadata.purge_started_at is not None else None

    def admit_and_record_legal_hold(
        self,
        *,
        document_id: str,
        legal_hold: LegalHoldRecord,
    ) -> ArchiveDocumentMetadata | None:
        """Admit, insert the hold and refresh the summary in ONE transaction.

        The three writes used to be three transactions, and the gap between the
        first two was a real hole: admission committed `legal_hold_status =
        active`, and until the INSERT landed a competing purge could recount
        active holds, find **none**, write `clear`, and delete the object. The
        hold row then arrived and the caller was told the hold succeeded --
        PURGED metadata, one ACTIVE hold, absent bytes, and a lifecycle-action
        answer of LEGAL_HOLD over a document that no longer existed.

        Atomicity is the database's, not the service's, for the same reason
        `apply_lifecycle_transition` gives: a compensating action after a
        partial failure has to be written by the process that just failed.

        The recount runs inside the transaction and counts the row this
        statement inserted, so the summary can never describe a set of holds
        that excludes the one being admitted.
        """
        now = datetime.now(timezone.utc)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE archive_documents
                SET legal_hold_status = 'active', updated_at = %s
                WHERE document_id = %s
                  AND purge_started_at IS NULL
                RETURNING *
                """,
                (now, document_id),
            )
            if cursor.fetchone() is None:
                return None
            cursor.execute(_SAVE_LEGAL_HOLD_SQL, _values(legal_hold, _LEGAL_HOLD_COLUMNS))
            cursor.execute(
                """
                UPDATE archive_documents
                SET legal_hold_count = (
                        SELECT count(*) FROM archive_legal_holds
                        WHERE document_id = %s AND hold_status = 'active'
                    ),
                    updated_at = %s
                WHERE document_id = %s
                RETURNING *
                """,
                (document_id, now, document_id),
            )
            row = cursor.fetchone()
        return ArchiveDocumentMetadata.model_validate(row) if row is not None else None

    def mark_purge_eligible(
        self,
        *,
        document_id: str,
        eligible_at: datetime,
    ) -> ArchiveDocumentMetadata | None:
        """Grant eligibility conditionally, on the stored row.

        Eligibility is the transition that grants permission to destroy, so it
        carries the hold guard as well as the irreversibility guards. The
        previous form read a snapshot, decided, and saved the whole document
        back: a hold committed between the read and the write had its summary
        columns overwritten from the stale snapshot, and the document was then
        deleted with an ACTIVE hold record standing against it.

        `COALESCE` keeps the first eligibility timestamp rather than restamping
        it, so a re-evaluation cannot make an old decision look recent.

        The NOT EXISTS belt mirrors `begin_purge`: eligibility grants permission
        to destroy, so a legacy active hold ROW vetoes it even when a historic
        race left the summary column saying clear (issue #166).
        """
        now = datetime.now(timezone.utc)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE archive_documents
                SET purge_status = 'eligible',
                    purge_eligible_at = COALESCE(purge_eligible_at, %s),
                    updated_at = %s
                WHERE document_id = %s
                  AND purge_started_at IS NULL
                  AND purge_status <> 'purged'
                  AND legal_hold_status <> 'active'
                  AND NOT EXISTS (
                      SELECT 1 FROM archive_legal_holds
                      WHERE document_id = %s AND hold_status = 'active'
                  )
                RETURNING *
                """,
                (eligible_at, now, document_id, document_id),
            )
            row = cursor.fetchone()
        return ArchiveDocumentMetadata.model_validate(row) if row is not None else None

    def mark_purge_not_eligible(
        self,
        *,
        document_id: str,
    ) -> ArchiveDocumentMetadata | None:
        """Withdraw eligibility. Protective, so it carries no hold guard.

        This is the transition taken *because* a hold is active, so requiring
        the absence of one would refuse exactly the case it exists to serve. It
        still refuses a started or completed purge: withdrawing eligibility from
        a document whose bytes are gone would rewrite the record to say
        destruction was never permitted.
        """
        now = datetime.now(timezone.utc)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE archive_documents
                SET purge_status = 'not_eligible', updated_at = %s
                WHERE document_id = %s
                  AND purge_started_at IS NULL
                  AND purge_status <> 'purged'
                RETURNING *
                """,
                (now, document_id),
            )
            row = cursor.fetchone()
        return ArchiveDocumentMetadata.model_validate(row) if row is not None else None

    def complete_purge(
        self,
        *,
        document_id: str,
        purged_at: datetime,
    ) -> ArchiveDocumentMetadata | None:
        """Record destruction against the stored row, never from a snapshot.

        Requires a claimed intent: completing a purge nobody began would assert
        a destruction no writer ordered. `purged_at` is set only once, so a
        retry that finishes an interrupted purge does not restamp the moment the
        bytes actually went.
        """
        now = datetime.now(timezone.utc)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE archive_documents
                SET purge_status = 'purged',
                    purged_at = COALESCE(purged_at, %s),
                    updated_at = %s
                WHERE document_id = %s
                  AND purge_started_at IS NOT NULL
                RETURNING *
                """,
                (purged_at, now, document_id),
            )
            row = cursor.fetchone()
        return ArchiveDocumentMetadata.model_validate(row) if row is not None else None

    def refresh_legal_hold_summary(
        self,
        document_id: str,
    ) -> ArchiveDocumentMetadata | None:
        """Recount from the hold rows AT WRITE TIME, under the document row lock.

        The previous port took a status and count the service had derived from
        an earlier read and wrote them unconditionally in a later transaction.
        A hold admitted between that read and this write was overwritten with
        the stale CLEAR/0 - and `begin_purge` trusts exactly this column, so the
        stale recount re-armed destruction against an ACTIVE hold (issue #166).

        The FOR UPDATE is what makes the derivation current rather than merely
        repository-owned: every hold writer locks the document row for its whole
        transaction, so once this lock is granted the recount statement's
        snapshot contains every committed hold write, and any concurrent
        admission or release waits until this commits. Without the lock, this
        statement could block mid-execution on a concurrent admission and then
        still evaluate its subquery against the pre-admission snapshot -
        PostgreSQL READ COMMITTED re-checks a blocked UPDATE's WHERE clause, not
        its subqueries.
        """
        now = datetime.now(timezone.utc)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM archive_documents WHERE document_id = %s FOR UPDATE",
                (document_id,),
            )
            locked = cursor.fetchone()
            if locked is None:
                return None
            cursor.execute(_REFRESH_HOLD_SUMMARY_SQL, (now, document_id, document_id))
            row = cursor.fetchone()
        return ArchiveDocumentMetadata.model_validate(row if row is not None else locked)

    def release_and_record_legal_hold(
        self,
        *,
        document_id: str,
        legal_hold_id: str,
        released_by: str,
        released_at: datetime,
        release_reason: str,
    ) -> tuple[LegalHoldRecord, ArchiveDocumentMetadata] | None:
        """Release the hold row and recount the summary in ONE transaction.

        The mirror of `admit_and_record_legal_hold`, and the same lock order:
        document row first, then hold rows. As two transactions - write the
        hold row, refresh from a separate read - the refresh raced a concurrent
        admission and wrote a stale CLEAR/0 over it (issue #166).

        The release itself is conditional on `hold_status = 'active'`, so
        releasing an already-released hold converges on the recorded release
        facts rather than restamping them. None means the hold does not exist
        for this document; the caller owns that refusal.
        """
        now = datetime.now(timezone.utc)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT document_id FROM archive_documents WHERE document_id = %s FOR UPDATE",
                (document_id,),
            )
            if cursor.fetchone() is None:
                return None
            cursor.execute(
                """
                UPDATE archive_legal_holds
                SET hold_status = 'clear',
                    released_by = %s,
                    released_at = %s,
                    release_reason = %s
                WHERE legal_hold_id = %s AND document_id = %s AND hold_status = 'active'
                RETURNING *
                """,
                (released_by, released_at, release_reason, legal_hold_id, document_id),
            )
            hold_row = cursor.fetchone()
            if hold_row is None:
                cursor.execute(
                    "SELECT * FROM archive_legal_holds "
                    "WHERE legal_hold_id = %s AND document_id = %s",
                    (legal_hold_id, document_id),
                )
                hold_row = cursor.fetchone()
                if hold_row is None:
                    return None
            cursor.execute(_REFRESH_HOLD_SUMMARY_SQL, (now, document_id, document_id))
            document_row = cursor.fetchone()
            if document_row is None:
                cursor.execute(
                    "SELECT * FROM archive_documents WHERE document_id = %s",
                    (document_id,),
                )
                document_row = cursor.fetchone()
        if document_row is None:  # pragma: no cover - the row is locked above
            return None
        return (
            LegalHoldRecord.model_validate(hold_row),
            ArchiveDocumentMetadata.model_validate(document_row),
        )

    def list_legal_holds(self, document_id: str) -> list[LegalHoldRecord]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM archive_legal_holds WHERE document_id = %s ORDER BY requested_at",
                (document_id,),
            )
            rows = cursor.fetchall()
        return [LegalHoldRecord.model_validate(row) for row in rows]

    def apply_lifecycle_transition(
        self,
        *,
        source_document_id: str,
        target_document_id: str,
        transition_type: LifecycleTransitionType,
        relationship: LifecycleRelationshipRecord,
    ) -> tuple[LifecycleRelationshipRecord, ArchiveDocumentMetadata, ArchiveDocumentMetadata]:
        """Lock both rows, re-validate the STORED state, write only decided columns.

        The previous shape wrote two caller snapshots whole through the guarded
        upsert. Its immutability guard excluded every MUTABLE_DOCUMENT_FIELD, so
        purge intent/timestamps/status and hold status/count were written from
        snapshots read before the service's validation - a purge or hold that
        committed in between was silently reverted (issue #166). Now:

        * both document rows are locked FOR UPDATE in sorted id order, so two
          transitions touching the same pair cannot deadlock and the
          preconditions are validated against rows no other writer can move;
        * the preconditions run on the LOCKED rows via the same domain policy
          the service uses for its fast refusal;
        * the writes name exactly the columns this transition decides -
          `superseded_by_document_id`, the transition's origin field and
          `updated_at` - plus the relationship row, all in one transaction.

        An exact replay - both stored pointers already record this transition
        and its relationship row exists - converges on the recorded
        relationship instead of conflicting.
        """
        if transition_type not in _TARGET_ORIGIN_UPDATE_SQL:
            raise UnsupportedLifecycleTransitionError("unsupported lifecycle transition")
        now = datetime.now(timezone.utc)
        with self._connect() as connection, connection.cursor() as cursor:
            locked: dict[str, ArchiveDocumentMetadata] = {}
            for document_id in sorted({source_document_id, target_document_id}):
                cursor.execute(
                    "SELECT * FROM archive_documents WHERE document_id = %s FOR UPDATE",
                    (document_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise DocumentNotFoundError("archive document was not found")
                locked[document_id] = ArchiveDocumentMetadata.model_validate(row)
            source = locked[source_document_id]
            target = locked[target_document_id]
            if transition_pointers_agree(
                source=source, target=target, transition_type=transition_type
            ):
                cursor.execute(
                    "SELECT * FROM archive_lifecycle_relationships "
                    "WHERE source_document_id = %s AND target_document_id = %s "
                    "AND transition_type = %s",
                    (source_document_id, target_document_id, transition_type.value),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    return (
                        LifecycleRelationshipRecord.model_validate(existing),
                        source,
                        target,
                    )
            validate_lifecycle_preconditions(
                source=source, target=target, transition_type=transition_type
            )
            try:
                cursor.execute(
                    "UPDATE archive_documents "
                    "SET superseded_by_document_id = %s, updated_at = %s "
                    "WHERE document_id = %s RETURNING *",
                    (target_document_id, now, source_document_id),
                )
                source_row = cursor.fetchone()
                cursor.execute(
                    _TARGET_ORIGIN_UPDATE_SQL[transition_type],
                    (source_document_id, now, target_document_id),
                )
                target_row = cursor.fetchone()
                cursor.execute(_SAVE_LIFECYCLE_SQL, _values(relationship, _LIFECYCLE_COLUMNS))
            except UniqueViolation as exc:
                # Unreachable through concurrent writers - the second
                # transaction re-validates on the locked rows and refuses
                # first. Reachable through LEGACY drift: the old whole-row
                # save could clear `superseded_by_document_id` while the
                # relationship row survived, so the one-successor/one-origin
                # indexes are the last guard standing for that pair. A typed
                # conflict, not a raw driver error.
                raise SupersessionConflictError(
                    "document already has a recorded lifecycle relationship"
                ) from exc
        if source_row is None or target_row is None:  # pragma: no cover - rows locked above
            raise DocumentNotFoundError("archive document was not found")
        return (
            relationship,
            ArchiveDocumentMetadata.model_validate(source_row),
            ArchiveDocumentMetadata.model_validate(target_row),
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
