"""Every persisted model field has a column, derived from the model (archive#146).

`migration_gate.py` checked a hand-maintained list of 15 names against the 58
fields on `ArchiveDocumentMetadata`, and the other 43 were checked by nothing.
Every column happened to exist, so this closes a liveness gap rather than a live
defect -- but the gate could not have told us if one did not.

The consequence is not a degraded feature. `postgres_repository.py` builds its
column list straight from the model:

    _DOCUMENT_COLUMNS = tuple(ArchiveDocumentMetadata.model_fields)

so a model field with no column is an INSERT naming a column that does not
exist, and **every write to `archive_documents` fails** on PostgreSQL. It is
invisible to the suite that runs against the in-memory repository, which has no
schema at all.

Two decisions worth stating, because the obvious implementations of each are
wrong:

**Derived, not restated.** The model is the authority on what gets persisted, so
the requirement is read from it. A second hand-written list cannot disagree with
the first usefully -- both live in this repository and both get updated by
whoever remembers.

**Column names are parsed, not substring-matched.** The old gate asked whether a
field name appeared anywhere in the DDL text, which `checksum` satisfies from
`checksum_algorithm`, and `purge_status` from a comment mentioning it. Comments
are stripped and real identifiers are extracted, so a field is only covered by a
column actually named for it.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "migrations"
sys.path.insert(0, str(ROOT / "src"))

from app.archive.audit import AccessAuditEvent  # noqa: E402
from app.archive.models import (  # noqa: E402
    ArchiveDocumentMetadata,
    LegalHoldRecord,
    LifecycleRelationshipRecord,
)


@dataclass(frozen=True)
class PersistedTable:
    """A table, and the model whose fields become its columns."""

    table: str
    model_name: str
    fields: frozenset[str]


#: Model to the table that persists it. The same pairing `postgres_repository`
#: makes when it derives each `_COLUMNS` tuple; stated once here so the gate
#: protects exactly the mapping the writer relies on.
#:
#: Field names are read from the concrete models at import, not held as a second
#: list -- the models remain the authority, and a field added to one appears
#: here without anybody remembering to add it.
PERSISTED_TABLES = (
    PersistedTable(
        "archive_documents",
        ArchiveDocumentMetadata.__name__,
        frozenset(ArchiveDocumentMetadata.model_fields),
    ),
    PersistedTable(
        "archive_legal_holds",
        LegalHoldRecord.__name__,
        frozenset(LegalHoldRecord.model_fields),
    ),
    PersistedTable(
        "archive_lifecycle_relationships",
        LifecycleRelationshipRecord.__name__,
        frozenset(LifecycleRelationshipRecord.model_fields),
    ),
    PersistedTable(
        "archive_access_audit",
        AccessAuditEvent.__name__,
        frozenset(AccessAuditEvent.model_fields),
    ),
)

_LINE_COMMENT = re.compile(r"--[^\n]*")
_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
#: One `ALTER TABLE` may carry several `ADD COLUMN` clauses, and only the first
#: follows the table name -- migration 009 adds five columns in one statement.
#: Matching `ALTER TABLE ... ADD COLUMN <name>` in a single pattern finds one of
#: them and silently reports the rest as absent, which is what this gate did on
#: its first run.
_ALTER_TABLE = re.compile(r"ALTER\s+TABLE\s+(\w+)(.*?);", re.IGNORECASE | re.DOTALL)
_ADD_COLUMN = re.compile(
    r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
    re.IGNORECASE,
)
#: Words that open a table-level clause rather than name a column.
_NOT_A_COLUMN = {
    "primary",
    "foreign",
    "unique",
    "check",
    "constraint",
    "exclude",
    "like",
}


def _columns_by_table() -> dict[str, set[str]]:
    """Column names per table, across every migration in order.

    The union matters: `purge_started_at` arrives in `012`, not in `001`, so a
    per-file check would refuse a column that is genuinely present. Comments are
    stripped first -- `012`'s own comment names `purge_document`,
    `legal_hold_active` and `purge_started_at` in prose, and a text search would
    count all three as columns.
    """
    tables: dict[str, set[str]] = {}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        ddl = _LINE_COMMENT.sub("", path.read_text(encoding="utf-8"))
        for table, body in _CREATE_TABLE.findall(ddl):
            tables.setdefault(table.lower(), set()).update(_column_names(body))
        for table, statement in _ALTER_TABLE.findall(ddl):
            added = {column.lower() for column in _ADD_COLUMN.findall(statement)}
            if added:
                tables.setdefault(table.lower(), set()).update(added)
    return tables


def _column_names(body: str) -> set[str]:
    """The first identifier of each top-level definition in a CREATE TABLE body.

    Split at depth zero so a `NUMERIC(18, 2)` or a multi-column `UNIQUE (a, b)`
    does not fragment into pieces that look like column definitions.
    """
    columns: set[str] = set()
    for definition in _split_top_level(body):
        head = definition.strip().split()
        if not head:
            continue
        name = head[0].strip('"').lower()
        if name in _NOT_A_COLUMN:
            continue
        columns.add(name)
    return columns


def _split_top_level(body: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in body:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(char)
    parts.append("".join(current))
    return parts


def main() -> int:
    tables = _columns_by_table()
    failures: list[str] = []

    for persisted in PERSISTED_TABLES:
        columns = tables.get(persisted.table)
        if columns is None:
            failures.append(f"{persisted.table}: no migration creates this table")
            continue
        missing = sorted(persisted.fields - columns)
        if missing:
            failures.append(
                f"{persisted.table}: {persisted.model_name} persists fields with no column: "
                + ", ".join(missing)
            )

    if failures:
        print("Migration schema coverage failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        print(
            "\nEvery field on a persisted model becomes a column in "
            "postgres_repository's INSERT. A field with no column fails every "
            "write to that table, and the in-memory repository the suite uses "
            "has no schema to catch it.",
            file=sys.stderr,
        )
        return 1

    covered = sum(len(persisted.fields) for persisted in PERSISTED_TABLES)
    print(
        f"Migration schema coverage passed: {covered} persisted fields across "
        f"{len(PERSISTED_TABLES)} tables, each backed by a column."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
