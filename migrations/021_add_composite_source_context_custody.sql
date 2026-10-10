-- Admit source-context v8 without rewriting retained v1-v7 rows. Apply after 020.
-- Pure JSON uniqueness guard: no source lookup, authority inference or calculation.
CREATE OR REPLACE FUNCTION archive_custody_unique_pin_keys(pins jsonb, key_path text[])
RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT CASE WHEN jsonb_typeof(pins) = 'array' THEN (
        SELECT count(*) = count(DISTINCT item #> key_path)
        FROM jsonb_array_elements(pins) item
    ) ELSE FALSE END
$$;

-- Retain the exact primary window subvector for each optional financial pin.
CREATE OR REPLACE FUNCTION archive_custody_product_windows_agree(identity jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT CASE
        WHEN NOT (identity ? 'source_products') THEN TRUE
        WHEN jsonb_typeof(identity->'source_products') <> 'array'
          OR jsonb_typeof(identity->'selection'->'windows') IS DISTINCT FROM 'array' THEN FALSE
        ELSE NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(identity->'source_products') product
            WHERE CASE WHEN jsonb_typeof(product#>'{pin,selection,windows}') = 'array' THEN (
                (product#>'{pin,selection,windows}') = (
                    SELECT coalesce(jsonb_agg(window_pin ORDER BY ordinal), '[]'::jsonb)
                    FROM jsonb_array_elements(identity->'selection'->'windows') WITH ORDINALITY AS w(window_pin, ordinal)
                    WHERE window_pin->>'period_start' >= product#>>'{pin,selection,period_start}'
                      AND window_pin->>'period_end' <= product#>>'{pin,selection,period_end}'
                )
                AND CASE product#>>'{pin,kind}'
                    WHEN 'CALENDAR_RETURN' THEN (
                        jsonb_array_length(product#>'{pin,selection,windows}') = 12
                        AND jsonb_typeof(product#>'{pin,year}') = 'number'
                        AND product#>>'{pin,selection,period_start}' = lpad(product#>>'{pin,year}', 4, '0') || '-01-01'
                        AND product#>>'{pin,selection,period_end}' = lpad(product#>>'{pin,year}', 4, '0') || '-12-31'
                    )
                    WHEN 'TRAILING_RETURN' THEN (
                        jsonb_typeof(product#>'{pin,months}') = 'number'
                        AND
                        jsonb_array_length(product#>'{pin,selection,windows}')::text = product#>>'{pin,months}'
                        AND product#>>'{pin,selection,period_end}' = identity#>>'{selection,period_end}'
                    ) ELSE FALSE END
            ) ELSE FALSE END IS NOT TRUE
        )
    END
$$;

ALTER TABLE archive_documents DROP CONSTRAINT IF EXISTS archive_documents_scope_check;
ALTER TABLE archive_documents ADD CONSTRAINT archive_documents_scope_check CHECK (
    (report_type = 'composite_review' AND portfolio_scope = 'composite'
     AND portfolio_id IS NULL AND composite_id IS NOT NULL AND length(trim(composite_id)) > 0
     AND composite_report_identity IS NOT NULL
     AND jsonb_typeof(composite_report_identity) = 'object'
     AND ((template_version = 'v7' AND (composite_report_identity->>'qualification' = 'CONTROLLED_HISTORICAL_POLICY_EVIDENCE_REPLAY') IS TRUE)
          OR (template_version = 'v6' AND (composite_report_identity->>'qualification' = 'CONTROLLED_MONTHLY_SOURCE_AMENDMENT_REPLAY') IS TRUE)
          OR (template_version = 'v4' AND (composite_report_identity->>'qualification' = 'CONTROLLED_ELIGIBILITY_SOURCE_REPLAY') IS TRUE)
          OR (template_version IN ('v1', 'v2', 'v3', 'v5', 'v8') AND (composite_report_identity->>'qualification' = 'EXPLICIT_RETAINED_CALCULATED_REPLAY') IS TRUE))
     AND (composite_report_identity->>'publication_state' = 'NOT_ATTESTED') IS TRUE
     AND (composite_report_identity->'selection'->>'tenant_id' = tenant_id) IS TRUE
     AND as_of_date = reporting_period_end
     AND report_revision_id IS NOT NULL AND document_reference IS NOT NULL
     AND declared_artifact_sha256 IS NOT NULL
     AND template_id = 'composite-review' AND template_version IN ('v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8')
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
         (template_version = 'v8'
          AND (composite_report_identity->'selection'->>'composite_id' = composite_id) IS TRUE
          AND (composite_report_identity->'selection'->>'period_start' = reporting_period_start::text) IS TRUE
          AND (composite_report_identity->'selection'->>'period_end' = reporting_period_end::text) IS TRUE
          AND (composite_report_identity->>'series_digest' ~ '^[0-9a-f]{64}$') IS TRUE
          AND (composite_report_identity->>'source_revision_digest' ~ '^[0-9a-f]{64}$') IS TRUE
          AND (composite_report_identity->>'factual_content_digest' ~ '^[0-9a-f]{64}$') IS TRUE
          AND (composite_report_identity->'selection'->>'reporting_currency' ~ '^[A-Z]{3}$') IS TRUE
          AND (composite_report_identity->'selection'->>'return_view' IN ('GROSS','NET_ACTUAL','NET_MODEL_FEE')) IS TRUE
          AND (composite_report_identity->'selection'->>'calculation_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS TRUE
          AND (composite_report_identity->'selection'->>'calculation_fingerprint' ~ '^sha256:[0-9a-f]{64}$') IS TRUE
          AND (composite_report_identity->'selection'->>'response_digest' ~ '^sha256:[0-9a-f]{64}$') IS TRUE
          AND (composite_report_identity->'selection'->>'methodology' ~ '^[^\s]{1,128}$') IS TRUE
          AND (composite_report_identity->'selection'->>'engine_version' ~ '^[^\s]{1,128}$') IS TRUE
          AND (jsonb_typeof(composite_report_identity->'definition') = 'object') IS TRUE
          AND (jsonb_typeof(composite_report_identity->'definition'->'pin') = 'object') IS TRUE
          AND (composite_report_identity->'definition'->'pin'->>'definition_version' ~ '^[^\s]{1,128}$') IS TRUE
          AND (composite_report_identity->'definition'->'pin'->>'content_hash' ~ '^sha256:[0-9a-f]{64}$') IS TRUE
          AND (composite_report_identity->'definition'->'pin'->>'response_digest' ~ '^sha256:[0-9a-f]{64}$') IS TRUE
          AND (composite_report_identity->'definition'->>'source_response_digest' = composite_report_identity->'definition'->'pin'->>'response_digest') IS TRUE
          AND (jsonb_typeof(composite_report_identity->'source_context') = 'object') IS TRUE
          AND (composite_report_identity->'source_context'->'definition' = composite_report_identity->'definition'->'pin') IS TRUE
          AND (jsonb_typeof(composite_report_identity->'source_context'->'since_inception') = 'boolean') IS TRUE
          AND CASE WHEN jsonb_typeof(composite_report_identity->'source_context'->'memberships') = 'array' THEN (
              jsonb_array_length(composite_report_identity->'source_context'->'memberships') BETWEEN 0 AND 2
              AND archive_custody_unique_pin_keys(composite_report_identity->'source_context'->'memberships', ARRAY['membership_revision'])
              AND ((composite_report_identity->'source_context'->'since_inception' = 'true'::jsonb)
                   OR jsonb_array_length(composite_report_identity->'source_context'->'memberships') > 0)
              AND jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                  '$.source_context.memberships[*] ? (@.membership_revision like_regex "^[^\\s]{1,128}$" && @.content_hash like_regex "^sha256:[0-9a-f]{64}$" && @.response_digest like_regex "^sha256:[0-9a-f]{64}$")'))
                  = jsonb_array_length(composite_report_identity->'source_context'->'memberships')
              AND (jsonb_array_length(composite_report_identity->'source_context'->'memberships') < 2
                   OR (composite_report_identity->'source_context'->'memberships'->0->>'membership_revision'
                       <> composite_report_identity->'source_context'->'memberships'->1->>'membership_revision') IS TRUE)
          ) ELSE FALSE END
          AND CASE WHEN jsonb_typeof(composite_report_identity->'selection'->'windows') = 'array' THEN (
              jsonb_array_length(composite_report_identity->'selection'->'windows') BETWEEN 1 AND 120
              AND archive_custody_unique_pin_keys(composite_report_identity->'selection'->'windows', ARRAY['materialization_id'])
              AND (composite_report_identity->'selection'->'windows'->0->>'period_start' = reporting_period_start::text) IS TRUE
              AND (composite_report_identity->'selection'->'windows'->-1->>'period_end' = reporting_period_end::text) IS TRUE
              AND jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                  '$.selection.windows[*] ? (@.materialization_id like_regex "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$" && @.definition_content_hash == $.definition.pin.content_hash && @.membership_content_hash like_regex "^sha256:[0-9a-f]{64}$" && @.attestation_content_hash like_regex "^sha256:[0-9a-f]{64}$" && @.retained_receipt_fingerprint like_regex "^sha256:[0-9a-f]{64}$" && @.source_cut_id like_regex "^[^\\s]{1,128}$" && @.restatement_sequence.type() == "number" && @.restatement_sequence >= 1)'))
                  = jsonb_array_length(composite_report_identity->'selection'->'windows')
              AND (jsonb_array_length(composite_report_identity->'source_context'->'memberships') = 0
                   OR jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                       '$.selection.windows[*] ? (@.membership_content_hash == $.source_context.memberships[0].content_hash || @.membership_content_hash == $.source_context.memberships[1].content_hash)'))
                       = jsonb_array_length(composite_report_identity->'selection'->'windows'))
          ) ELSE FALSE END
          AND (NOT (composite_report_identity ? 'source_products') OR CASE
              WHEN jsonb_typeof(composite_report_identity->'source_products') = 'array' THEN (
                  jsonb_array_length(composite_report_identity->'source_products') BETWEEN 0 AND 8
                  AND archive_custody_unique_pin_keys(composite_report_identity->'source_products', ARRAY['pin','product_key'])
                  AND archive_custody_product_windows_agree(composite_report_identity)
                  AND jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                      '$.source_products[*] ? ((@.pin.kind == "CALENDAR_RETURN" || @.pin.kind == "TRAILING_RETURN") && @.pin.product_key like_regex "^[a-z][a-z0-9_]{0,63}$" && @.source_response_digest like_regex "^sha256:[0-9a-f]{64}$" && @.source_response_digest == @.pin.selection.response_digest && @.pin.selection.tenant_id == $.selection.tenant_id && @.pin.selection.composite_id == $.selection.composite_id && @.pin.selection.reporting_currency == $.selection.reporting_currency && @.pin.selection.return_view == $.selection.return_view && @.pin.selection.methodology == $.selection.methodology && @.pin.selection.engine_version == $.selection.engine_version && @.pin.selection.windows.type() == "array" && @.pin.selection.windows.size() >= 1 && @.pin.selection.windows.size() <= 120)'))
                      = jsonb_array_length(composite_report_identity->'source_products')
                  AND jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                      '$.source_products[*].pin.selection.windows[*] ? (@.definition_content_hash != $.definition.pin.content_hash)')) = 0
              ) ELSE FALSE END)
         )
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
         OR
         (template_version = 'v4'
          AND NOT (composite_report_identity ? 'source_products')
          AND NOT (composite_report_identity->'selection' ? 'calculation_id')
          AND NOT (composite_report_identity->'selection' ? 'windows')
          AND NOT (composite_report_identity->'selection' ? 'source_request')
          AND (composite_report_identity->'selection'->>'composite_id' = composite_id) IS TRUE
          AND (composite_report_identity->'selection'->>'period_start' = reporting_period_start::text) IS TRUE
          AND (composite_report_identity->'selection'->>'period_end' = reporting_period_end::text) IS TRUE
          AND (length(composite_report_identity->'selection'->>'definition_version') BETWEEN 1 AND 128) IS TRUE
          AND (composite_report_identity->'selection'->>'reporting_currency' ~ '^[A-Z]{3}$') IS TRUE
          AND EXTRACT(DAY FROM reporting_period_start) = 1
          AND reporting_period_end = (date_trunc('month', reporting_period_end) + INTERVAL '1 month - 1 day')::date
          AND CASE
              WHEN jsonb_typeof(composite_report_identity->'selection'->'months') = 'array'
              THEN (jsonb_array_length(composite_report_identity->'selection'->'months') BETWEEN 1 AND 120
               AND (composite_report_identity->'selection'->'months'->0->>'month' = left(reporting_period_start::text, 7)) IS TRUE
               AND (composite_report_identity->'selection'->'months'->-1->>'month' = left(reporting_period_end::text, 7)) IS TRUE
               AND jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                   '$.selection.months[*] ? (@.evidence_kind == "PUBLISHED" || @.evidence_kind == "EVALUATED_ONLY")'))
                   = jsonb_array_length(composite_report_identity->'selection'->'months'))
              ELSE FALSE END)
         OR
         (template_version = 'v6'
          AND NOT (composite_report_identity ? 'source_products')
          AND NOT (composite_report_identity->'selection' ? 'calculation_id')
          AND NOT (composite_report_identity->'selection' ? 'windows')
          AND NOT (composite_report_identity->'selection' ? 'source_request')
          AND (composite_report_identity->'selection'->>'composite_id' = composite_id) IS TRUE
          AND (composite_report_identity->'selection'->>'period_start' = reporting_period_start::text) IS TRUE
          AND (composite_report_identity->'selection'->>'period_end' = reporting_period_end::text) IS TRUE
          AND (length(composite_report_identity->'selection'->>'definition_version') BETWEEN 1 AND 128) IS TRUE
          AND (composite_report_identity->'selection'->>'reporting_currency' ~ '^[A-Z]{3}$') IS TRUE
          AND EXTRACT(DAY FROM reporting_period_start) = 1
          AND reporting_period_end = (date_trunc('month', reporting_period_end) + INTERVAL '1 month - 1 day')::date
          AND CASE
              WHEN jsonb_typeof(composite_report_identity->'selection'->'months') = 'array'
              THEN (jsonb_array_length(composite_report_identity->'selection'->'months') BETWEEN 1 AND 120
               AND (composite_report_identity->'selection'->'months'->0->>'month' = left(reporting_period_start::text, 7)) IS TRUE
               AND (composite_report_identity->'selection'->'months'->-1->>'month' = left(reporting_period_end::text, 7)) IS TRUE
               AND jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                   '$.selection.months[*] ? (@.evidence_kind == "PUBLISHED" || @.evidence_kind == "EVALUATED_ONLY")'))
                   = jsonb_array_length(composite_report_identity->'selection'->'months'))
              ELSE FALSE END
          AND (composite_report_identity->'selection'->>'selection_version' = 'v2') IS TRUE
          AND CASE
              WHEN jsonb_typeof(composite_report_identity->'selection'->'months') = 'array'
              THEN (
                  jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                      '$.selection.months[*] ? (@.lineage_receipts.type() == "array" && @.lineage_receipts.size() >= 1 && @.lineage_receipts.size() <= 31)'))
                      = jsonb_array_length(composite_report_identity->'selection'->'months')
                  AND jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                      '$.selection.months[*] ? (@.evidence_kind == "EVALUATED_ONLY" || (@.evidence_kind == "PUBLISHED" && @.parent_publication_response_digest like_regex "^sha256:[0-9a-f]{64}$"))'))
                      = jsonb_array_length(composite_report_identity->'selection'->'months')
                  AND jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                      '$.selection.months[*].lineage_receipts[*]'))
                      = jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                          '$.selection.months[*].lineage_receipts[*] ? ((@.product_version == "v1" || @.product_version == "v2") && @.evaluation_revision like_regex "^[^\\s]{1,128}$" && @.approval_content_hash like_regex "^sha256:[0-9a-f]{64}$" && @.receipt_content_hash like_regex "^sha256:[0-9a-f]{64}$" && @.receipt_response_digest like_regex "^sha256:[0-9a-f]{64}$")'))
              ) ELSE FALSE END)
         OR
         (template_version = 'v7'
          AND NOT (composite_report_identity ? 'source_products')
          AND NOT (composite_report_identity->'selection' ? 'calculation_id')
          AND NOT (composite_report_identity->'selection' ? 'windows')
          AND NOT (composite_report_identity->'selection' ? 'source_request')
          AND (composite_report_identity->'selection'->>'composite_id' = composite_id) IS TRUE
          AND (composite_report_identity->'selection'->>'period_start' = reporting_period_start::text) IS TRUE
          AND (composite_report_identity->'selection'->>'period_end' = reporting_period_end::text) IS TRUE
          AND (length(composite_report_identity->'selection'->>'definition_version') BETWEEN 1 AND 128) IS TRUE
          AND (composite_report_identity->'selection'->>'reporting_currency' ~ '^[A-Z]{3}$') IS TRUE
          AND EXTRACT(DAY FROM reporting_period_start) = 1
          AND reporting_period_end = (date_trunc('month', reporting_period_end) + INTERVAL '1 month - 1 day')::date
          AND CASE
              WHEN jsonb_typeof(composite_report_identity->'selection'->'months') = 'array'
              THEN (jsonb_array_length(composite_report_identity->'selection'->'months') BETWEEN 1 AND 120
               AND (composite_report_identity->'selection'->'months'->0->>'month' = left(reporting_period_start::text, 7)) IS TRUE
               AND (composite_report_identity->'selection'->'months'->-1->>'month' = left(reporting_period_end::text, 7)) IS TRUE
               AND jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                   '$.selection.months[*] ? (@.evidence_kind == "PUBLISHED" || @.evidence_kind == "EVALUATED_ONLY")'))
                   = jsonb_array_length(composite_report_identity->'selection'->'months'))
              ELSE FALSE END
          AND (composite_report_identity->'selection'->>'selection_version' = 'v3') IS TRUE
          AND (composite_report_identity->>'calculation_boundary' = 'Configured-identity controlled producer custody only; no cryptographic or bank provenance acceptance, TWR, MWR, dispersion, contribution or model-fee calculation. CONTROLLED / NOT_ATTESTED.') IS TRUE
          AND CASE
              WHEN jsonb_typeof(composite_report_identity->'selection'->'months') = 'array'
              THEN (
                  jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                      '$.selection.months[*] ? ((@.product_version == "v3" && !exists(@.lineage_receipts) && !exists(@.parent_publication_response_digest)) || (@.product_version == "v4" && @.lineage_receipts.type() == "array" && @.lineage_receipts.size() >= 1 && @.lineage_receipts.size() <= 31 && @.lineage_receipts[last].product_version == "v3" && (@.evidence_kind == "EVALUATED_ONLY" || @.parent_publication_response_digest like_regex "^sha256:[0-9a-f]{64}$")))'))
                      = jsonb_array_length(composite_report_identity->'selection'->'months')
                  AND jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                      '$.selection.months[*].lineage_receipts[*] ? (@.product_version == "v3")'))
                      = jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                          '$.selection.months[*] ? (@.product_version == "v4")'))
                  AND jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                      '$.selection.months[*].lineage_receipts[*]'))
                      = jsonb_array_length(jsonb_path_query_array(composite_report_identity,
                          '$.selection.months[*].lineage_receipts[*] ? ((@.product_version == "v3" || @.product_version == "v4") && @.evaluation_revision like_regex "^[^\\s]{1,128}$" && @.approval_content_hash like_regex "^sha256:[0-9a-f]{64}$" && @.receipt_content_hash like_regex "^sha256:[0-9a-f]{64}$" && @.receipt_response_digest like_regex "^sha256:[0-9a-f]{64}$")'))
              ) ELSE FALSE END)
         OR
         (template_version = 'v5'
          AND NOT (composite_report_identity ? 'source_products')
          AND NOT (composite_report_identity->'selection' ? 'windows')
          AND NOT (composite_report_identity->'selection' ? 'months')
          AND NOT (composite_report_identity->'selection' ? 'source_request')
          AND (composite_report_identity->'selection'->>'composite_id' = composite_id) IS TRUE
          AND (composite_report_identity->'selection'->>'period_start' = reporting_period_start::text) IS TRUE
          AND (composite_report_identity->'selection'->>'period_end' = reporting_period_end::text) IS TRUE
          AND reporting_period_end > reporting_period_start
          AND (composite_report_identity->'selection'->>'reporting_currency' ~ '^[A-Z]{3}$') IS TRUE
          AND (composite_report_identity->'selection'->>'schema_version' = 'composite-pooled-mwr.v1') IS TRUE
          AND (composite_report_identity->'selection'->>'metric_id' = 'POOLED_MONEY_WEIGHTED_RETURN') IS TRUE
          AND (composite_report_identity->'selection'->>'method' = 'XIRR:v1') IS TRUE
          AND (composite_report_identity->'selection'->>'fallback_policy' IN ('REQUIRE_XIRR', 'ALLOW_MODIFIED_DIETZ')) IS TRUE
          AND (composite_report_identity->'selection'->>'calculation_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS TRUE
          AND (composite_report_identity->'selection'->>'response_digest' ~ '^sha256:[0-9a-f]{64}$') IS TRUE
          AND (composite_report_identity->'selection'->>'source_bundle_digest' ~ '^sha256:[0-9a-f]{64}$') IS TRUE
          AND (composite_report_identity->'selection'->>'input_manifest_digest' ~ '^sha256:[0-9a-f]{64}$') IS TRUE
          AND (
              ((jsonb_typeof(composite_report_identity->'selection'->'correction_of_calculation_id') = 'null') IS TRUE
               AND (jsonb_typeof(composite_report_identity->'selection'->'predecessor_response_digest') = 'null') IS TRUE)
              OR
              ((composite_report_identity->'selection'->>'correction_of_calculation_id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') IS TRUE
               AND (composite_report_identity->'selection'->>'predecessor_response_digest' ~ '^sha256:[0-9a-f]{64}$') IS TRUE
               AND (composite_report_identity->'selection'->>'correction_of_calculation_id'
                    <> composite_report_identity->'selection'->>'calculation_id') IS TRUE)
          )
          AND CASE
              WHEN jsonb_typeof(composite_report_identity->'selection'->'source_pins') = 'array'
               AND jsonb_typeof(composite_report_identity->'selection'->'expected_portfolio_ids') = 'array'
              THEN (jsonb_array_length(composite_report_identity->'selection'->'source_pins') BETWEEN 1 AND 128
               AND jsonb_array_length(composite_report_identity->'selection'->'expected_portfolio_ids') BETWEEN 1 AND 10000)
              ELSE FALSE END)
     )
     AND output_format = 'xlsx'
     AND mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    OR
    (report_type <> 'composite_review' AND portfolio_scope <> 'composite'
     AND portfolio_id IS NOT NULL AND composite_id IS NULL AND composite_report_identity IS NULL)
);
