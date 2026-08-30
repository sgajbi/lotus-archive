ALTER TABLE archive_documents
    ADD COLUMN IF NOT EXISTS advisor_commentary JSONB;
