# Archive Service Boundaries

`lotus-archive` is the generated-document archive service for Lotus reporting flows. It is not a
general-purpose file store and it does not own report generation, rendering, batch scheduling, or
customer document delivery.

## Current Implementation Posture

RFC-0103 Slice 5 establishes the internal archive API surface for authorized Lotus callers:
generated-document archival, support-safe metadata lookup, checksum-verified binary download,
access-audit lookup, retention posture lookup, purge eligibility and execution, and legal-hold
set/release with purge blocking. Lifecycle relationships, report handoff, gateway retrieval, and
Workbench product features are not supported yet.

## Authoritative Boundaries

| Boundary | Owner | Current posture |
| --- | --- | --- |
| Report request and job identity | `lotus-report` | Upstream source for future archive records |
| Snapshot and lineage reference | `lotus-report` | Upstream source for future archive records |
| Render attempt and artifact metadata | `lotus-render` through `lotus-report` | Upstream source for future archive records |
| Archived document identity | `lotus-archive` | Implemented through metadata model and archive API |
| Binary storage | `lotus-archive` | Implemented through storage adapter and controlled download API |
| Access audit | `lotus-archive` | Implemented for archive create, metadata read, binary download, access-event read, retention read, purge evaluation, purge execution, legal-hold set/release, and authorization denial |
| Retention and purge | `lotus-archive` | Implemented for retention posture, purge eligibility, governed purge execution, and post-purge support-safe metadata |
| Legal hold | `lotus-archive` | Implemented for legal-hold set/release, authority reference, active-hold summary, and purge blocking |
| Product-facing retrieval | `lotus-gateway` | Deferred until gateway facade is implemented |
| Workbench retrieval surface | `lotus-workbench` | Not supported unless gateway-backed retrieval is implemented |

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
archive caller. Gateway-backed product retrieval remains future work and must be implemented in
`lotus-gateway` before any Workbench retrieval surface is claimed.

RFC-0103 Slice 5 adds:

1. `GET /documents/{document_id}/retention` for authorized retention, purge, and legal-hold
   posture lookup.
2. `POST /documents/{document_id}/purge-evaluation` for support-safe purge eligibility evaluation.
3. `POST /documents/{document_id}/purge` for governed purge execution after retention expiry.
4. `POST /documents/{document_id}/legal-holds` for setting a legal hold with authority reference.
5. `DELETE /documents/{document_id}/legal-holds/{legal_hold_id}` for releasing a legal hold and
   refreshing purge-blocking posture.

These APIs remain internal Lotus service APIs. They do not establish report-to-archive handoff,
gateway retrieval, Workbench retrieval, or customer-facing document delivery.

## Documentation Ownership

1. `README.md` is the quick-start and current support posture entrypoint.
2. `docs/architecture/` owns implementation-facing architecture and boundary decisions.
3. `docs/supported-features.md` owns implementation-backed feature posture.
4. `docs/runbooks/` owns operator procedures.
5. `wiki/` owns published operator and support-facing summary material.
