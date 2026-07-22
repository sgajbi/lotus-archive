ALTER TABLE archive_documents
    ADD COLUMN IF NOT EXISTS idea_evidence_pack JSONB;
