-- Admit linked v3 without rewriting retained v1/v2 rows. Apply only after 015.
ALTER TABLE archive_documents DROP CONSTRAINT IF EXISTS archive_documents_scope_check;
ALTER TABLE archive_documents ADD CONSTRAINT archive_documents_scope_check CHECK (
    (report_type = 'composite_review' AND portfolio_scope = 'composite'
     AND portfolio_id IS NULL AND composite_id IS NOT NULL AND length(trim(composite_id)) > 0
     AND composite_report_identity IS NOT NULL
     AND jsonb_typeof(composite_report_identity) = 'object'
     AND (composite_report_identity->>'qualification' = 'EXPLICIT_RETAINED_CALCULATED_REPLAY') IS TRUE
     AND (composite_report_identity->>'publication_state' = 'NOT_ATTESTED') IS TRUE
     AND (composite_report_identity->'selection'->>'tenant_id' = tenant_id) IS TRUE
     AND as_of_date = reporting_period_end
     AND report_revision_id IS NOT NULL AND document_reference IS NOT NULL
     AND declared_artifact_sha256 IS NOT NULL
     AND template_id = 'composite-review' AND template_version IN ('v1', 'v2', 'v3')
     AND report_data_contract_version = 'composite_review.' || template_version
     AND (composite_report_identity->>'contract_version' = report_data_contract_version) IS TRUE
     AND (
         (template_version IN ('v1', 'v2')
          AND (composite_report_identity->'selection'->>'composite_id' = composite_id) IS TRUE
          AND (composite_report_identity->'selection'->>'period_start' = reporting_period_start::text) IS TRUE
          AND (composite_report_identity->'selection'->>'period_end' = reporting_period_end::text) IS TRUE
          AND (template_version = 'v1' OR CASE
              WHEN jsonb_typeof(composite_report_identity->'source_products') = 'array'
              THEN jsonb_array_length(composite_report_identity->'source_products') BETWEEN 1 AND 8
              ELSE FALSE END))
         OR
         (template_version = 'v3'
          AND NOT (composite_report_identity ? 'source_products')
          AND (composite_report_identity->'selection'->'source_request'->>'composite_id' = composite_id) IS TRUE
          AND (composite_report_identity->'selection'->'source_request'->>'period_start' = reporting_period_start::text) IS TRUE
          AND (composite_report_identity->'selection'->'source_request'->>'period_end' = reporting_period_end::text) IS TRUE
          AND (composite_report_identity->'selection'->'source_request'->>'metric_id' = 'LINKED_MEMBER_CONTRIBUTION') IS TRUE
          AND (composite_report_identity->'selection'->'source_request'->>'method' = 'CARINO:v1') IS TRUE
          AND (NOT (composite_report_identity->'selection'->'source_request' ? 'restatement_sequence')
               OR (jsonb_typeof(composite_report_identity->'selection'->'source_request'->'restatement_sequence') = 'null') IS TRUE)
          AND CASE
              WHEN jsonb_typeof(composite_report_identity->'selection'->'windows') = 'array'
               AND jsonb_typeof(composite_report_identity->'selection'->'source_request'->'materialization_ids') = 'array'
              THEN (jsonb_array_length(composite_report_identity->'selection'->'windows') BETWEEN 1 AND 120
               AND jsonb_array_length(composite_report_identity->'selection'->'source_request'->'materialization_ids')
                   = jsonb_array_length(composite_report_identity->'selection'->'windows')
               AND (composite_report_identity->'selection'->'source_request'->'materialization_ids'
                    = jsonb_path_query_array(composite_report_identity, '$.selection.windows[*].materialization_id')) IS TRUE
               AND (composite_report_identity->'selection'->'windows'->0->>'period_start' = reporting_period_start::text) IS TRUE
               AND (composite_report_identity->'selection'->'windows'->-1->>'period_end' = reporting_period_end::text) IS TRUE)
              ELSE FALSE END)
     )
     AND output_format = 'xlsx'
     AND mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    OR
    (report_type <> 'composite_review' AND portfolio_scope <> 'composite'
     AND portfolio_id IS NOT NULL AND composite_id IS NULL AND composite_report_identity IS NULL)
);
