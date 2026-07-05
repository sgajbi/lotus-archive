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


def test_initial_migration_enforces_archive_state_invariants() -> None:
    migration = (ROOT / "migrations" / "001_create_archive_documents.sql").read_text(
        encoding="utf-8"
    )

    assert (
        "report_type IN ('portfolio_review', 'outcome_review', 'proof_pack', 'rebalance_wave')"
        in (migration)
    )
    assert "checksum_algorithm = 'sha256'" in migration
    assert "classification IN ('internal', 'confidential', 'restricted')" in migration
    assert "purge_status IN ('not_eligible', 'eligible', 'purged')" in migration
    assert "legal_hold_status IN ('clear', 'active')" in migration
    assert "CHECK (reporting_period_start <= reporting_period_end)" in migration
    assert "retention_start_date <= retain_until_date" in migration
    assert "purge_status = 'purged' AND purged_at IS NOT NULL" in migration
    assert (
        "num_nonnulls(supersedes_document_id, correction_of_document_id, reissue_of_document_id) <= 1"
        in (migration)
    )
    assert "superseded_by_document_id <> document_id" in migration


def test_reviewed_advisory_narrative_migration_contains_required_field() -> None:
    migration = (
        ROOT / "migrations" / "004_add_reviewed_advisory_narrative_to_archive_documents.sql"
    ).read_text(encoding="utf-8")

    assert "reviewed_advisory_narrative JSONB" in migration
    assert "ADD COLUMN IF NOT EXISTS" in migration


def test_advisor_proposal_memo_migration_contains_required_field() -> None:
    migration = (
        ROOT / "migrations" / "005_add_advisor_proposal_memo_to_archive_documents.sql"
    ).read_text(encoding="utf-8")

    assert "advisor_proposal_memo JSONB" in migration
    assert "ADD COLUMN IF NOT EXISTS" in migration


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
    assert "hold_status IN ('active', 'clear')" in migration
    assert "hold_status = 'active' AND released_by IS NULL" in migration
    assert "hold_status = 'clear' AND released_by IS NOT NULL" in migration


def test_lifecycle_relationship_migration_contains_required_fields() -> None:
    migration = (ROOT / "migrations" / "003_create_archive_lifecycle_relationships.sql").read_text(
        encoding="utf-8"
    )

    for field in [
        "lifecycle_relationship_id",
        "source_document_id",
        "target_document_id",
        "transition_type",
        "transition_reason",
        "requested_by",
        "requested_at",
    ]:
        assert field in migration
    assert migration.count("REFERENCES archive_documents(document_id)") == 2
    assert "transition_type IN ('supersede', 'correct', 'reissue')" in migration
    assert "CHECK (source_document_id <> target_document_id)" in migration
    assert "uq_archive_lifecycle_relationships_one_successor" in migration
    assert "uq_archive_lifecycle_relationships_one_origin" in migration
