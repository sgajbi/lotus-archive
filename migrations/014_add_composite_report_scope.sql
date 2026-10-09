-- Composite scope is exclusive; historical portfolio rows are not rewritten.
ALTER TABLE archive_documents ADD COLUMN IF NOT EXISTS composite_id TEXT;
ALTER TABLE archive_documents ADD COLUMN IF NOT EXISTS composite_report_identity JSONB;
ALTER TABLE archive_documents ALTER COLUMN portfolio_id DROP NOT NULL;
ALTER TABLE archive_documents DROP CONSTRAINT IF EXISTS archive_documents_report_type_check;
ALTER TABLE archive_documents ADD CONSTRAINT archive_documents_report_type_check CHECK (
    report_type IN ('portfolio_review', 'outcome_review', 'proof_pack', 'rebalance_wave', 'composite_review')
);
ALTER TABLE archive_documents DROP CONSTRAINT IF EXISTS archive_documents_scope_check;
ALTER TABLE archive_documents ADD CONSTRAINT archive_documents_scope_check CHECK (
    (report_type = 'composite_review' AND portfolio_scope = 'composite'
     AND portfolio_id IS NULL AND composite_id IS NOT NULL AND length(trim(composite_id)) > 0
     AND composite_report_identity IS NOT NULL
     AND jsonb_typeof(composite_report_identity) = 'object'
     AND (composite_report_identity->>'contract_version' = 'composite_review.v1') IS TRUE
     AND (composite_report_identity->>'qualification' = 'EXPLICIT_RETAINED_CALCULATED_REPLAY') IS TRUE
     AND (composite_report_identity->>'publication_state' = 'NOT_ATTESTED') IS TRUE
     AND (composite_report_identity->'selection'->>'composite_id' = composite_id) IS TRUE
     AND (composite_report_identity->'selection'->>'tenant_id' = tenant_id) IS TRUE
     AND (composite_report_identity->'selection'->>'period_start' = reporting_period_start::text) IS TRUE
     AND (composite_report_identity->'selection'->>'period_end' = reporting_period_end::text) IS TRUE
     AND as_of_date = reporting_period_end
     AND report_revision_id IS NOT NULL AND document_reference IS NOT NULL
     AND declared_artifact_sha256 IS NOT NULL
     AND template_id = 'composite-review' AND template_version = 'v1'
     AND report_data_contract_version = 'composite_review.v1' AND output_format = 'xlsx'
     AND mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    OR
    (report_type <> 'composite_review' AND portfolio_scope <> 'composite'
     AND portfolio_id IS NOT NULL AND composite_id IS NULL AND composite_report_identity IS NULL)
);
