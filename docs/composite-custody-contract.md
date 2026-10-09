# Composite report custody

Archive accepts the first `composite_review` XLSX family through the existing
`POST /documents` route. Report owns selection, snapshot and revision identity;
Render is the sole transmit authority and supplies actual artifact SHA-256 and
render provenance. Archive independently verifies bytes and retains evidence.
Retention grants no financial approval. Joined source-qualified producer
acceptance remains separate from component proof under issue #176. The
[delivery ledger](composite-custody-delivery-ledger.md) records the subsequent
normal supported producer's bounded actual HTTP original, financially corrected
and technical rerender custody. Controlled Performance intake/verifier and
`NOT_ATTESTED` qualification remain explicit.

## Identity dictionary

| Field | Owner and invariant |
| --- | --- |
| `portfolio_scope` | `composite` for this family; existing string portfolio scopes remain compatible. |
| `portfolio_id` | Null for composite reports; required for existing report families. Never a fabricated Core portfolio. |
| `composite_id` | Report's exact source composite identifier. Required exclusively for `composite_review`. |
| `report_job_id`, `report_request_id`, `snapshot_id` | Existing Report lifecycle identifiers, retained verbatim. |
| `report_revision_id`, `document_reference` | Existing opaque Report revision and document identity; mandatory for composite custody. |
| `render_job_id`, `render_attempt_id` | Render-owned job and byte-derived attempt identity. |
| `archive_request_id` | Existing Render idempotency identity; exact duplicate returns the original record, conflicting metadata/bytes refuses. |
| `declared_artifact_sha256`, `checksum` | Render-declared and independently Archive-measured SHA-256 must agree before storage or duplicate replay. |
| `composite_report_identity` | Immutable typed source-safe selection and three bare 64-hex Report lifecycle digests. |

`composite_report_identity` contains `contract_version=composite_review.v1`,
`qualification=EXPLICIT_RETAINED_CALCULATED_REPLAY`,
`publication_state=NOT_ATTESTED`, `selection`, `series_digest`,
`source_revision_digest`, and `factual_content_digest`. Unknown summary fields
and invented authority states refuse. A future official authority contract
requires a separately governed extension; no control revision is invented here.

Selection preserves Report's exact `tenant_id`, `composite_id`, `calculation_id`,
inclusive `period_start`/`period_end`, `reporting_currency`, `return_view`,
`methodology`, `engine_version`, `calculation_fingerprint`, `response_digest`,
and ordered `windows`. Each window retains `materialization_id`, dates,
`restatement_sequence`, definition/membership/attestation content hashes,
`source_cut_id`, `method_binding`, and `retained_receipt_fingerprint`.
The source's attestation hash is a retained universe pin, not an approval grant.
One to 120 unique contiguous windows cover the exact horizon. Scope, tenant,
period and as-of date must agree with Archive metadata. Archive performs no
financial recomputation, latest-source lookup or publication qualification.

## Format, scope and event contracts

The admitted tuple is `composite-review` / `v1` / `composite_review.v1` / `xlsx`
with `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
Archive verifies a real OOXML ZIP workbook, content types, workbook/worksheet
XML and relationships before storage. At most 4,096 ZIP parts and 128 MiB
expanded data are admitted within the existing decoded request-size limit.
Ambiguous ZIP entries, unsafe paths, encryption, XML declarations and external
workbook relationships refuse. Existing PDF and other family behavior stays
compatible; no existing bytes or identities are relabelled.

Composite creation requires trusted caller tenant/region matching the offered
metadata. Existing persisted-scope authorization applies to metadata, binary,
events, retention, legal hold, purge and every lifecycle successor. Denials are
audited. Downloads verify retained SHA-256 and return the XLSX MIME and extension.
Source events expose composite scope, selection pins, opaque Report revision,
document reference, MIME/format and checksum-backed artifact refs; they contain
no workbook bytes, financial dataset, storage key or client reference.
Portfolio-only downstream consumers must explicitly recognize composite scope or
refuse this family; they must never derive a portfolio identifier from composite
identity. Existing portfolio events keep their non-null portfolio identifier.

Migration `014_add_composite_report_scope.sql` adds nullable `composite_id` and
JSONB identity, relaxes `portfolio_id` nullability only with an exclusive scope
constraint, and expands the report-family constraint. Historical rows remain
unchanged. Apply all ordered migrations using the established migration flow;
deploy the schema before admitting new composite requests. Rollback disables
new admissions while preserving existing composite rows and bytes; never drop
their columns or restore portfolio non-nullability over retained history.

## Requests, downloads and retained revisions

The executable external product journey is
`tests/e2e/test_composite_custody_journey.py`, calling the shared scenario in
`tests/integration/test_composite_custody_api.py` with the full source-shaped
metadata in `tests/fixtures/composite_custody.py` and a valid synthetic OOXML
workbook. It submits the actual registered API and independently checks real
filesystem bytes, MIME, extension, checksum, event qualification, correction,
audit and retention. This is a synthetic component example, not an actual
Performance→Report→Render chain or a sample approved financial report.

For an actual Render-produced package, Report populates `render_context.archive`
with this metadata; Render overlays its owned custody fields and invokes Archive.
After HTTP 201, authorized Report/Gateway callers use:

```http
GET /documents/{document_id}
GET /documents/{document_id}/download
GET /documents/{document_id}/source-events
X-Caller-Service: lotus-report
X-Actor-Type: service
X-Actor-Id: report-worker
X-Tenant-Id: <admitted tenant>
X-Region: <admitted region>
X-Correlation-Id: <request correlation>
X-Trace-Id: <request trace>
```

Check downloaded bytes against returned SHA-256 before use. Metadata and events
continue to disclose `NOT_ATTESTED`. `GET /documents/{original}/download` returns
the retained original after correction; `GET /documents/{original}/current`
resolves the corrected document. Rerender preserves Report snapshot/revision;
corrected source facts require a new snapshot/revision and existing
`POST /documents/{original}/correct` or `/supersede` relationship. Neither action
deletes the original nor releases its retention/legal hold.

## Retry and validation runbook

On an unobserved ingest result, reuse the exact request and artifact identity.
Resolve using the existing archive-request metadata lookup; do not mint another
identity or treat timeout as proof of absence. A retry after metadata repository
reconstruction returns the same document. Changed bytes or pins under an existing
request return conflict. Invalid format returns `400 metadata_validation_failed`;
declared checksum mismatch returns `422 declared_checksum_mismatch`;
typed metadata refusal returns `422 validation_failed`. Cross-tenant reads and
composite writes return `403 authorization_failed`; missing scope returns 401.
Storage and lifecycle failures keep existing bounded error semantics and fences.

Run from the Archive repository root on Windows:

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_composite_identity.py tests/unit/test_archive_artifact_format.py tests/integration/test_composite_custody_api.py
.venv/Scripts/python.exe -m pytest tests/e2e/test_composite_custody_journey.py
.venv/Scripts/python.exe -m pytest tests/integration/test_postgres_composite_custody.py
```

On Linux/macOS, replace `.venv/Scripts/python.exe` with `.venv/bin/python`.
The PostgreSQL command requires `LOTUS_ARCHIVE_TEST_DATABASE_URL`; governed CI
sets `LOTUS_ARCHIVE_REQUIRE_DATABASE_PROOF=1` so absent database proof fails.
No local skip is durable adapter evidence. All twelve report products, official
authority, GIPS publication, joined live acceptance and enterprise capacity
remain separately unproven.
