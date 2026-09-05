-- report#283 revision identity: the canonical revision reference for the
-- facts an archived document presents rides custody verbatim, so a document
-- can be joined to its report revision without replaying Report policy.
-- Opaque, never parsed. NULL for documents delivered before the identity
-- existed - history is never relabelled.
ALTER TABLE archive_documents
    ADD COLUMN IF NOT EXISTS report_revision_id TEXT;
