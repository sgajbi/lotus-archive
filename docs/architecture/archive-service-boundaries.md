# Archive Service Boundaries

`lotus-archive` is the generated-document archive service for Lotus reporting flows. It is not a
general-purpose file store and it does not own report generation, rendering, batch scheduling, or
customer document delivery.

## Current Implementation Posture

RFC-0103 establishes the supported first-wave archive API surface for authorized Lotus callers:
generated-document archival, support-safe metadata lookup, checksum-verified binary download,
access-audit lookup, retention posture lookup, purge eligibility and execution, and legal-hold
set/release with purge blocking, lifecycle relationships, current-document resolution, and
report-to-archive handoff after successful PDF render. Gateway-backed retrieval is supported through
`lotus-gateway` as the product-facing boundary, and Workbench archive retrieval is supported only
through the Workbench BFF and Gateway route. The archive metadata contract now accepts only governed
generated-report types: `portfolio_review`, `outcome_review`, `proof_pack`, and
`rebalance_wave`.

## Authoritative Boundaries

| Boundary | Owner | Current posture |
| --- | --- | --- |
| Report request and job identity | `lotus-report` | Implemented as source-backed archive handoff metadata after successful PDF render |
| Snapshot and lineage reference | `lotus-report` | Implemented as source-backed archive handoff metadata after successful PDF render |
| Render attempt and artifact metadata | `lotus-render` through `lotus-report` | Implemented as source-backed archive handoff metadata after successful PDF render |
| Generated report type support | `lotus-archive` | Implemented through explicit metadata validation for `portfolio_review`, `outcome_review`, `proof_pack`, and `rebalance_wave` |
| Archived document identity | `lotus-archive` | Implemented through metadata model and archive API |
| Binary storage | `lotus-archive` | Implemented through storage adapter and controlled download API |
| Access audit | `lotus-archive` | Implemented for archive create, metadata read, binary download, access-event read, retention read, purge evaluation, purge execution, legal-hold set/release, and authorization denial |
| Retention and purge | `lotus-archive` | Implemented for retention posture, purge eligibility, governed purge execution, and post-purge support-safe metadata |
| Legal hold | `lotus-archive` | Implemented for legal-hold set/release, authority reference, active-hold summary, and purge blocking |
| Lifecycle relationships | `lotus-archive` | Implemented for supersession, correction, reissue, append-only relationship records, historical lookup, and current-document resolution |
| Product-facing retrieval | `lotus-gateway` | Supported through gateway metadata and controlled download routes |
| Workbench retrieval surface | `lotus-workbench` | Supported only through the Workbench BFF and existing gateway-backed retrieval boundary; direct Workbench-to-archive calls remain unsupported |

## Module Families

The implementation should remain organized around these module families:

1. `metadata`: archived document identity, source-backed metadata, and support-safe lookup.
2. `storage`: object storage abstraction, checksum verification, and binary retrieval boundary.
3. `audit`: access and lifecycle audit records for archive reads and mutations.
4. `retention`: retention policy assignment, purge eligibility, and support-safe purge evidence.
5. `legal_hold`: legal hold set, release, authority reference, and purge blocking.
6. `lifecycle`: supersession, correction, reissue, and historical document relationships.

These boundaries should be preserved as the service grows. Avoid placing storage behavior in API
routers, retention policy logic in report handoff code, or gateway/product assumptions in the
archive core.

## Storage Posture

The RFC target architecture is PostgreSQL metadata plus S3-compatible object storage behind an
adapter. Development adapters are allowed only behind the same abstraction. Local filesystem storage
must not become product architecture and must not be exposed as a direct path in APIs or logs.

RFC-0103 Slice 3 adds the first internal implementation of this posture:

1. `migrations/001_create_archive_documents.sql` defines the PostgreSQL archive-document metadata
   contract.
2. `src/app/archive/models.py` defines the source-backed metadata model used by the service core.
3. `src/app/archive/storage.py` defines the object-storage protocol and filesystem development
   adapter.
4. `src/app/archive/archive_writer.py` combines metadata validation, checksum enforcement,
   idempotency, repository persistence, and storage writes.

These are internal service capabilities. They do not create public archive APIs or product-facing
retrieval support.

## Archive API Posture

RFC-0103 Slice 4 adds:

1. `POST /documents` for generated-document archival by authorized `lotus-report` callers.
2. `GET /documents/{document_id}` for support-safe metadata lookup by authorized Lotus callers.
3. `GET /documents/{document_id}/download` for archive-mediated binary download with checksum
   verification.
4. `GET /documents/{document_id}/access-events` for support investigation of archive access
   events.

All archive API routes require caller context. Workbench is intentionally not an authorized direct
archive caller. Gateway-backed product retrieval is implemented in `lotus-gateway`; Workbench
retrieval consumes that gateway boundary through the Workbench BFF and must not call
`lotus-archive` directly.

RFC-0103 Slice 5 adds:

1. `GET /documents/{document_id}/retention` for authorized retention, purge, and legal-hold
   posture lookup.
2. `POST /documents/{document_id}/purge-evaluation` for support-safe purge eligibility evaluation.
3. `POST /documents/{document_id}/purge` for governed purge execution after retention expiry.
4. `POST /documents/{document_id}/legal-holds` for setting a legal hold with authority reference.
5. `DELETE /documents/{document_id}/legal-holds/{legal_hold_id}` for releasing a legal hold and
   refreshing purge-blocking posture.

These APIs remain internal Lotus service APIs. Customer-facing document delivery is not supported.
Workbench retrieval is supported only through the Workbench BFF and gateway facade.

RFC-0103 Slice 6 adds:

1. `POST /documents/{document_id}/supersede` for recording that a target archived document
   supersedes the historical source document.
2. `POST /documents/{document_id}/correct` for recording that a target archived document corrects
   the historical source document.
3. `POST /documents/{document_id}/reissue` for recording that a target archived document reissues
   the historical source document.
4. `GET /documents/{document_id}/current` for resolving the current archived document while
   keeping direct historical metadata lookup available through `GET /documents/{document_id}`.

Lifecycle relationships are append-only audit-backed archive history. They do not delete,
overwrite, or hide historical document metadata.

RFC-0103 Slice 7 adds report-to-archive handoff in `lotus-report`:

1. successful PDF render jobs submit source-backed archive metadata and rendered artifact bytes to
   `POST /documents`.
2. report job status records `archiving` separately from `archived`.
3. archive validation, conflict, storage, and execution failures map to truthful report-job failure
   categories.
4. retrieval, retention execution, legal hold, purge, and lifecycle ownership remain in
   `lotus-archive`.

RFC-0040 proof-pack report artifacts use the same archive lifecycle once `lotus-report` supplies a
rendered proof-pack PDF and source-backed metadata with `report_type=proof_pack`,
`template_id=proof-pack`, and `report_data_contract_version=dpm_proof_pack_report_input.v1`.
`lotus-archive` preserves document identity, storage, retention, legal-hold, purge, lifecycle, and
access-audit truth; it does not reconstruct proof-pack sections, source hashes, or manage-owned
evidence.

RFC-0041 rebalance-wave report artifacts use the same archive lifecycle once `lotus-report`
supplies a rendered wave PDF and source-backed metadata with `report_type=rebalance_wave`,
`template_id=rebalance-wave`, and `report_data_contract_version=dpm_wave_report_input.v1`.
`lotus-archive` preserves document identity, storage, retention, legal-hold, purge, lifecycle, and
access-audit truth; it does not reconstruct wave membership, proof-pack posture, source hashes, or
wave events.

## Documentation Ownership

1. `README.md` is the quick-start and current support posture entrypoint.
2. `docs/architecture/` owns implementation-facing architecture and boundary decisions.
3. `docs/supported-features.md` owns implementation-backed feature posture.
4. `docs/runbooks/` owns operator procedures.
5. `wiki/` owns published operator and support-facing summary material.
