"""Structural facts about the migrations that no model declares (archive#146).

Field *coverage* moved to `migration_schema_coverage.py`, which derives the
requirement from the persisted models instead of restating fifteen of their
fifty-eight names here. What is left is the set of facts a model genuinely
cannot express: which columns are unique, which are stored as JSONB, which
tables reference which, that later migrations are additive, and that the
expected indexes exist.

Keeping those here is not a leftover. They are real assertions about the schema,
and unlike the field lists they are not a second copy of something the code
already declares.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "migrations"


def main() -> None:
    migration = MIGRATIONS_DIR / "001_create_archive_documents.sql"
    if not migration.exists():
        raise SystemExit("Migration gate failed: initial archive document migration is missing")

    ddl = migration.read_text(encoding="utf-8")
    if "archive_request_id TEXT NOT NULL UNIQUE" not in ddl:
        raise SystemExit("Migration gate failed: archive_request_id must be unique")
    if "storage_key TEXT NOT NULL UNIQUE" not in ddl:
        raise SystemExit("Migration gate failed: storage_key must be unique")
    reviewed_narrative_migration = (
        MIGRATIONS_DIR / "004_add_reviewed_advisory_narrative_to_archive_documents.sql"
    )
    if not reviewed_narrative_migration.exists():
        raise SystemExit("Migration gate failed: reviewed advisory narrative migration is missing")
    reviewed_narrative_ddl = reviewed_narrative_migration.read_text(encoding="utf-8")
    if "reviewed_advisory_narrative JSONB" not in reviewed_narrative_ddl:
        raise SystemExit(
            "Migration gate failed: reviewed_advisory_narrative must be stored as JSONB"
        )
    if "ADD COLUMN IF NOT EXISTS" not in reviewed_narrative_ddl:
        raise SystemExit(
            "Migration gate failed: reviewed_advisory_narrative migration must be additive"
        )

    legal_hold_migration = MIGRATIONS_DIR / "002_create_archive_legal_holds.sql"
    if not legal_hold_migration.exists():
        raise SystemExit("Migration gate failed: archive legal-hold migration is missing")
    legal_hold_ddl = legal_hold_migration.read_text(encoding="utf-8")
    if "REFERENCES archive_documents(document_id)" not in legal_hold_ddl:
        raise SystemExit("Migration gate failed: legal holds must reference archive documents")

    lifecycle_migration = MIGRATIONS_DIR / "003_create_archive_lifecycle_relationships.sql"
    if not lifecycle_migration.exists():
        raise SystemExit("Migration gate failed: archive lifecycle migration is missing")
    lifecycle_ddl = lifecycle_migration.read_text(encoding="utf-8")
    if lifecycle_ddl.count("REFERENCES archive_documents(document_id)") < 2:
        raise SystemExit(
            "Migration gate failed: lifecycle relationships must reference source and target documents"
        )

    access_audit_migration = MIGRATIONS_DIR / "007_create_archive_access_audit.sql"
    if not access_audit_migration.exists():
        raise SystemExit("Migration gate failed: archive access-audit migration is missing")
    access_audit_ddl = access_audit_migration.read_text(encoding="utf-8")
    if "idx_archive_access_audit_document_created" not in access_audit_ddl:
        raise SystemExit(
            "Migration gate failed: access audit must index document and creation time"
        )

    print("Migration gate passed")


if __name__ == "__main__":
    main()
