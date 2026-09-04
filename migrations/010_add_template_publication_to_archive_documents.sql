-- render#120 publication gating: the governed template posture at render
-- time rides custody so Report's external-publication gate can read it from
-- the archived record. Verbatim from Render's overlay - Archive never
-- interprets it.
ALTER TABLE archive_documents
    ADD COLUMN IF NOT EXISTS template_publication TEXT;
