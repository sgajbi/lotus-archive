-- archive#55 retention durability: destruction is irreversible and the record
-- of it was not. `purge_document` deleted the stored object and then recorded
-- the outcome, so a failure between the two left a document whose metadata
-- said retained and whose bytes were gone -- indistinguishable from a document
-- that was genuinely retained.
--
-- Worse, it was unrecoverable in one ordering: a legal hold applied in that
-- window is legitimate against the record, and the retry then correctly
-- refuses with legal_hold_active forever. Archive would go on issuing signed
-- LEGAL_HOLD decisions asserting the evidence was preserved under hold.
--
-- Set immediately before the delete and never cleared. NULL for every document
-- purged or retained before this column existed -- history is never relabelled,
-- and a NULL here means "no destruction was ever begun", which is true of them.
ALTER TABLE archive_documents
    ADD COLUMN IF NOT EXISTS purge_started_at TIMESTAMPTZ;
