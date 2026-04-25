-- RFC-0103 Slice 3: generated document archive metadata.
-- PostgreSQL target DDL; local tests use repository abstractions without changing this contract.

CREATE TABLE IF NOT EXISTS archive_documents (
    document_id TEXT PRIMARY KEY,
    archive_request_id TEXT NOT NULL UNIQUE,
    report_job_id TEXT NOT NULL,
    report_request_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    render_job_id TEXT NOT NULL,
    render_attempt_id TEXT NOT NULL,
    report_type TEXT NOT NULL,
    portfolio_scope TEXT NOT NULL,
    portfolio_id TEXT NOT NULL,
    client_reference TEXT,
    as_of_date DATE NOT NULL,
    reporting_period_start DATE NOT NULL,
    reporting_period_end DATE NOT NULL,
    frequency TEXT NOT NULL,
    template_id TEXT NOT NULL,
    template_version TEXT NOT NULL,
    render_service_version TEXT NOT NULL,
    report_data_contract_version TEXT NOT NULL,
    storage_provider TEXT NOT NULL,
    storage_namespace TEXT NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    checksum_algorithm TEXT NOT NULL,
    checksum TEXT NOT NULL,
    size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
    mime_type TEXT NOT NULL,
    output_format TEXT NOT NULL,
    classification TEXT NOT NULL,
    region TEXT NOT NULL,
    tenant_id TEXT,
    retention_policy_id TEXT,
    retention_start_date DATE,
    retain_until_date DATE,
    purge_eligible_at TIMESTAMPTZ,
    purged_at TIMESTAMPTZ,
    purge_status TEXT NOT NULL,
    legal_hold_status TEXT NOT NULL,
    legal_hold_count INTEGER NOT NULL CHECK (legal_hold_count >= 0),
    supersedes_document_id TEXT,
    superseded_by_document_id TEXT,
    correction_of_document_id TEXT,
    reissue_of_document_id TEXT,
    created_by_service TEXT NOT NULL,
    created_by_actor TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_archive_documents_report_job_id
    ON archive_documents (report_job_id);

CREATE INDEX IF NOT EXISTS idx_archive_documents_portfolio_id
    ON archive_documents (portfolio_id);

CREATE INDEX IF NOT EXISTS idx_archive_documents_storage_key
    ON archive_documents (storage_key);
