CREATE TABLE IF NOT EXISTS archive_legal_holds (
    legal_hold_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES archive_documents(document_id),
    hold_status TEXT NOT NULL CHECK (hold_status IN ('active', 'clear')),
    hold_reason TEXT NOT NULL,
    authority_reference TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    released_by TEXT,
    released_at TIMESTAMPTZ,
    release_reason TEXT,
    CHECK (
        (hold_status = 'active' AND released_by IS NULL AND released_at IS NULL AND release_reason IS NULL)
        OR (hold_status = 'clear' AND released_by IS NOT NULL AND released_at IS NOT NULL AND release_reason IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_archive_legal_holds_document_id
    ON archive_legal_holds (document_id);

CREATE INDEX IF NOT EXISTS idx_archive_legal_holds_status
    ON archive_legal_holds (hold_status);
