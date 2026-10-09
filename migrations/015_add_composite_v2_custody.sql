-- Admit version-matched v2 source products without rewriting retained v1 rows.
ALTER TABLE archive_documents DROP CONSTRAINT IF EXISTS archive_documents_scope_check;
ALTER TABLE archive_documents ADD CONSTRAINT archive_documents_scope_check CHECK (
    (report_type = 'composite_review' AND portfolio_scope = 'composite'
     AND portfolio_id IS NULL AND composite_id IS NOT NULL AND length(trim(composite_id)) > 0
     AND composite_report_identity IS NOT NULL
     AND jsonb_typeof(composite_report_identity) = 'object'
     AND (composite_report_identity->>'qualification' = 'EXPLICIT_RETAINED_CALCULATED_REPLAY') IS TRUE
     AND (composite_report_identity->>'publication_state' = 'NOT_ATTESTED') IS TRUE
     AND (composite_report_identity->'selection'->>'composite_id' = composite_id) IS TRUE
     AND (composite_report_identity->'selection'->>'tenant_id' = tenant_id) IS TRUE
     AND (composite_report_identity->'selection'->>'period_start' = reporting_period_start::text) IS TRUE
     AND (composite_report_identity->'selection'->>'period_end' = reporting_period_end::text) IS TRUE
     AND as_of_date = reporting_period_end
     AND report_revision_id IS NOT NULL AND document_reference IS NOT NULL
     AND declared_artifact_sha256 IS NOT NULL
     AND template_id = 'composite-review' AND template_version IN ('v1', 'v2')
     AND report_data_contract_version = 'composite_review.' || template_version
     AND (composite_report_identity->>'contract_version' = report_data_contract_version) IS TRUE
     AND (template_version = 'v1' OR CASE
         WHEN jsonb_typeof(composite_report_identity->'source_products') = 'array'
         THEN jsonb_array_length(composite_report_identity->'source_products') BETWEEN 1 AND 8
         ELSE FALSE END)
     AND output_format = 'xlsx'
     AND mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    OR
    (report_type <> 'composite_review' AND portfolio_scope <> 'composite'
     AND portfolio_id IS NOT NULL AND composite_id IS NULL AND composite_report_identity IS NULL)
);
