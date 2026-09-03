-- render#120 evidence chain: custody verification fields (archive#118).
-- document_reference names the governed document (minted by lotus-report,
-- printed in the artifact footer); document_id remains the stored record's
-- own identity - two facts, never collapsed. declared_artifact_sha256 is
-- what the caller claimed; checksum remains what Archive measured.
ALTER TABLE archive_documents
    ADD COLUMN IF NOT EXISTS document_reference TEXT,
    ADD COLUMN IF NOT EXISTS declared_artifact_sha256 TEXT,
    ADD COLUMN IF NOT EXISTS render_runtime_engine TEXT,
    ADD COLUMN IF NOT EXISTS render_runtime_engine_version TEXT,
    ADD COLUMN IF NOT EXISTS template_digest TEXT;

-- The collision check asks "who already holds these exact bytes"; the
-- reference lookup supports reconciliation by governed identity.
CREATE INDEX IF NOT EXISTS idx_archive_documents_checksum
    ON archive_documents (checksum);
CREATE INDEX IF NOT EXISTS idx_archive_documents_document_reference
    ON archive_documents (document_reference)
    WHERE document_reference IS NOT NULL;
