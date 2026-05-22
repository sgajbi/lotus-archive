-- RFC-0023 Slice 11D: support-safe reviewed advisory narrative archive metadata.
-- Stores package lineage and posture only; raw narrative sections remain report/render owned.

ALTER TABLE archive_documents
    ADD COLUMN IF NOT EXISTS reviewed_advisory_narrative JSONB;
