from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_initial_migration_contains_required_archive_document_fields() -> None:
    migration = (ROOT / "migrations" / "001_create_archive_documents.sql").read_text(
        encoding="utf-8"
    )

    for field in [
        "document_id",
        "archive_request_id",
        "report_job_id",
        "snapshot_id",
        "render_attempt_id",
        "storage_key",
        "checksum_algorithm",
        "checksum",
        "size_bytes",
        "retention_policy_id",
        "purge_status",
        "legal_hold_status",
        "legal_hold_count",
    ]:
        assert field in migration
    assert "archive_request_id TEXT NOT NULL UNIQUE" in migration
    assert "storage_key TEXT NOT NULL UNIQUE" in migration


def test_legal_hold_migration_contains_required_fields() -> None:
    migration = (ROOT / "migrations" / "002_create_archive_legal_holds.sql").read_text(
        encoding="utf-8"
    )

    for field in [
        "legal_hold_id",
        "document_id",
        "hold_status",
        "hold_reason",
        "authority_reference",
        "requested_by",
        "requested_at",
        "released_by",
        "released_at",
        "release_reason",
    ]:
        assert field in migration
    assert "REFERENCES archive_documents(document_id)" in migration
