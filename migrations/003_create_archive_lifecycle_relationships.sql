CREATE TABLE IF NOT EXISTS archive_lifecycle_relationships (
    lifecycle_relationship_id TEXT PRIMARY KEY,
    source_document_id TEXT NOT NULL REFERENCES archive_documents(document_id),
    target_document_id TEXT NOT NULL REFERENCES archive_documents(document_id),
    transition_type TEXT NOT NULL CHECK (transition_type IN ('supersede', 'correct', 'reissue')),
    transition_reason TEXT NOT NULL,
    transition_reason_code TEXT NOT NULL CHECK (
        transition_reason_code IN (
            'archive_document_supersession_requested',
            'archive_document_correction_requested',
            'client_delivery_reissue_requested'
        )
    ),
    requested_by TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    CHECK (source_document_id <> target_document_id)
);

CREATE INDEX IF NOT EXISTS idx_archive_lifecycle_relationships_source_document
    ON archive_lifecycle_relationships(source_document_id);

CREATE INDEX IF NOT EXISTS idx_archive_lifecycle_relationships_target_document
    ON archive_lifecycle_relationships(target_document_id);

CREATE INDEX IF NOT EXISTS idx_archive_lifecycle_relationships_transition_type
    ON archive_lifecycle_relationships(transition_type);

CREATE UNIQUE INDEX IF NOT EXISTS uq_archive_lifecycle_relationships_one_successor
    ON archive_lifecycle_relationships(source_document_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_archive_lifecycle_relationships_one_origin
    ON archive_lifecycle_relationships(target_document_id);
