CREATE TABLE IF NOT EXISTS archive_access_audit (
    audit_event_id TEXT PRIMARY KEY,
    document_id TEXT,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'archive_create',
            'metadata_read',
            'binary_download',
            'access_events_read',
            'retention_read',
            'purge_evaluation',
            'purge_execution',
            'legal_hold_set',
            'legal_hold_release',
            'lifecycle_supersede',
            'lifecycle_correct',
            'lifecycle_reissue',
            'current_document_read',
            'source_events_read',
            'batch_access_preflight',
            'idea_lifecycle_decision_read',
            'authorization_denied'
        )
    ),
    actor_type TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    caller_service TEXT NOT NULL,
    authorization_decision TEXT NOT NULL CHECK (
        authorization_decision IN ('allowed', 'denied')
    ),
    authorization_reason_code TEXT NOT NULL,
    operation_reason_code TEXT,
    correlation_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_archive_access_audit_document_created
    ON archive_access_audit (document_id, created_at);
