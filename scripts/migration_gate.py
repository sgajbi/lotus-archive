from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "migrations"

REQUIRED_FIELDS = {
    "document_id",
    "archive_request_id",
    "report_job_id",
    "report_request_id",
    "snapshot_id",
    "render_job_id",
    "render_attempt_id",
    "storage_key",
    "checksum_algorithm",
    "checksum",
    "size_bytes",
    "retention_policy_id",
    "purge_status",
    "legal_hold_status",
    "legal_hold_count",
}


def main() -> None:
    migration = MIGRATIONS_DIR / "001_create_archive_documents.sql"
    if not migration.exists():
        raise SystemExit("Migration gate failed: initial archive document migration is missing")

    ddl = migration.read_text(encoding="utf-8")
    missing_fields = sorted(field for field in REQUIRED_FIELDS if field not in ddl)
    if missing_fields:
        raise SystemExit(
            "Migration gate failed: missing archive document fields " + ", ".join(missing_fields)
        )
    if "archive_request_id TEXT NOT NULL UNIQUE" not in ddl:
        raise SystemExit("Migration gate failed: archive_request_id must be unique")
    if "storage_key TEXT NOT NULL UNIQUE" not in ddl:
        raise SystemExit("Migration gate failed: storage_key must be unique")

    print("Migration gate passed")


if __name__ == "__main__":
    main()
