# Archive Service Boundaries

`lotus-archive` is the generated-document archive service for Lotus reporting flows. It is not a
general-purpose file store and it does not own report generation, rendering, batch scheduling, or
customer document delivery.

## Current Implementation Posture

RFC-0103 Slice 1 establishes the repository and documentation structure for the archive domain. No
archive create, retrieval, retention, purge, legal-hold, lifecycle, gateway, or Workbench product
feature is supported yet.

## Authoritative Boundaries

| Boundary | Owner | Current posture |
| --- | --- | --- |
| Report request and job identity | `lotus-report` | Upstream source for future archive records |
| Snapshot and lineage reference | `lotus-report` | Upstream source for future archive records |
| Render attempt and artifact metadata | `lotus-render` through `lotus-report` | Upstream source for future archive records |
| Archived document identity | `lotus-archive` | Planned for metadata model slice |
| Binary storage | `lotus-archive` | Planned through storage adapter slice |
| Access audit | `lotus-archive` | Planned through audit model and API slices |
| Retention and purge | `lotus-archive` | Planned through retention slice |
| Legal hold | `lotus-archive` | Planned through legal-hold slice |
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

## Documentation Ownership

1. `README.md` is the quick-start and current support posture entrypoint.
2. `docs/architecture/` owns implementation-facing architecture and boundary decisions.
3. `docs/supported-features.md` owns implementation-backed feature posture.
4. `docs/runbooks/` owns operator procedures.
5. `wiki/` owns published operator and support-facing summary material.

