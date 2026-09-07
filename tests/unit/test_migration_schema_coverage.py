"""The schema-coverage gate fails on the schema drift it claims to catch (#146).

The gate it replaces passed on a schema it was not looking at: fifteen of
`ArchiveDocumentMetadata`'s fifty-eight fields were checked and forty-three were
not. Every column happened to exist, so nothing ever failed -- and a gate that
has never been seen to fail is a gate nobody has tested.

These exercise the parser against real DDL shapes taken from this repository's
own migrations rather than invented ones, because the first version of the gate
passed its own author's reading and still mis-parsed migration 009.
"""

from __future__ import annotations

import pytest

from scripts.migration_schema_coverage import (
    PERSISTED_TABLES,
    PersistedTable,
    _column_names,
    _columns_by_table,
    _split_top_level,
    main,
)

pytestmark = pytest.mark.governance


def test_the_real_migrations_cover_every_persisted_field() -> None:
    """The gate passes on the schema as it actually stands.

    Stated as its own test so a failure elsewhere in this file reads as a parser
    defect rather than as genuine drift.
    """
    tables = _columns_by_table()
    for persisted in PERSISTED_TABLES:
        assert persisted.fields <= tables[persisted.table], persisted.table
    assert main() == 0


def test_a_multi_clause_alter_table_contributes_every_column() -> None:
    """Migration 009 adds five columns in one statement, and only one follows
    the table name.

    The gate's first implementation matched `ALTER TABLE <t> ADD COLUMN <c>` as
    a single pattern, found `document_reference`, and reported the other four as
    having no column. It was a convincing failure: four specific, real field
    names, printed as drift, on a schema with no drift at all. A gate whose
    false positives look exactly like true ones is worse than no gate.
    """
    columns = _columns_by_table()["archive_documents"]

    for column in (
        "document_reference",
        "declared_artifact_sha256",
        "render_runtime_engine",
        "render_runtime_engine_version",
        "template_digest",
    ):
        assert column in columns, f"{column} is added by migration 009"


def test_a_column_added_by_a_later_migration_counts() -> None:
    """`purge_started_at` arrives in 012, not in 001.

    The replaced gate read one file per table, so deriving the field list from
    the model without also taking the union across migrations would have
    reported every later-added column as missing.
    """
    assert "purge_started_at" in _columns_by_table()["archive_documents"]


def test_a_prefix_of_a_real_column_is_not_satisfied_by_it() -> None:
    """The substring trap, closed.

    The replaced gate asked whether a name appeared anywhere in the DDL text, so
    a field called `checksum` was satisfied by the column `checksum_algorithm`,
    and `status` by `purge_status`. Parsing identifiers means a field is covered
    only by a column actually named for it.
    """
    columns = _column_names("checksum_algorithm TEXT NOT NULL, purge_status TEXT NOT NULL")

    assert columns == {"checksum_algorithm", "purge_status"}
    assert "checksum" not in columns
    assert "status" not in columns


def test_a_column_named_only_in_a_comment_does_not_count() -> None:
    """Prose is not schema.

    Migration 012's comment names `purge_document`, `legal_hold_active` and
    `purge_started_at` while adding exactly one column. A text search counts all
    three.
    """
    columns = _columns_by_table()

    assert "legal_hold_active" not in columns["archive_documents"]
    assert "purge_document" not in columns["archive_documents"]


def test_table_level_constraints_are_not_read_as_columns() -> None:
    """`PRIMARY KEY (a, b)` and `UNIQUE (a, b)` open clauses, not columns."""
    columns = _column_names(
        "document_id TEXT NOT NULL, tenant_id TEXT NOT NULL, "
        "PRIMARY KEY (document_id), UNIQUE (document_id, tenant_id)"
    )

    assert columns == {"document_id", "tenant_id"}


def test_a_parenthesised_type_does_not_fragment_into_columns() -> None:
    """`NUMERIC(18, 2)` contains a comma that is not a definition boundary."""
    assert _split_top_level("size_bytes NUMERIC(18, 2), storage_key TEXT") == [
        "size_bytes NUMERIC(18, 2)",
        " storage_key TEXT",
    ]


def test_the_gate_fails_when_a_persisted_field_has_no_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The falsification, run in-process rather than described.

    A model gains a field, no migration adds the column. On PostgreSQL this is
    an INSERT naming a column that does not exist, so every write to the table
    fails -- and the suite that runs against the in-memory repository, which has
    no schema, stays green throughout.
    """

    drifted = PersistedTable(
        "archive_documents",
        "DriftedModel",
        frozenset({"document_id", "a_field_no_migration_adds"}),
    )
    monkeypatch.setattr("scripts.migration_schema_coverage.PERSISTED_TABLES", (drifted,))

    assert main() == 1


def test_the_gate_fails_when_a_table_has_no_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other direction: a persisted model whose table was never created."""

    orphan = PersistedTable("a_table_nobody_created", "Model", frozenset({"document_id"}))
    monkeypatch.setattr("scripts.migration_schema_coverage.PERSISTED_TABLES", (orphan,))

    assert main() == 1
