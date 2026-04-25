# Supported Features

This document records implementation-backed support posture for `lotus-archive`.

## Current State

`lotus-archive` currently supports the governed service boundary scaffold plus the first internal
archive API surface:

1. FastAPI application shell.
2. Health, liveness, readiness, metadata, metrics, correlation headers, and trace headers.
3. Repository-native quality gates and CI baseline.
4. Archive-specific module-family and documentation structure.
5. Safe error envelope for service-level errors.
6. Caller-context parsing helper for future protected archive APIs.
7. Structured support-safe request logging.
8. Archive metadata model and PostgreSQL migration contract.
9. Filesystem-backed development storage adapter behind the object-storage abstraction.
10. SHA-256 checksum calculation and storage-time validation.
11. Idempotent archive-write domain service for duplicate archive requests.
12. Internal generated-document archive API for authorized `lotus-report` callers.
13. Controlled document metadata lookup for authorized Lotus callers.
14. Controlled document binary download with retrieval-time checksum verification.
15. Access-audit recording for archive create, metadata read, binary download, access-event read,
    and authorization denial.

No gateway-backed or Workbench-facing archive product feature is supported yet.

## Supported Internal Capabilities

| Capability | Support state | Backing implementation |
| --- | --- | --- |
| Generated-document archival | `ready` | `POST /documents`, `ArchiveWriter`, metadata model, storage adapter, checksum validation, and idempotency tests. |
| Controlled document metadata lookup | `ready` | `GET /documents/{document_id}` with caller-context enforcement, authorization, audit, and support-safe response model. |
| Controlled document binary download | `ready` | `GET /documents/{document_id}/download` with caller-context enforcement, authorization, storage retrieval, checksum verification, and audit. |
| Access audit for archive API actions | `ready` | In-memory first-wave access-audit repository and `GET /documents/{document_id}/access-events` for support investigation. |

## Not Yet Supported

| Capability | Support state | Reason |
| --- | --- | --- |
| Retention policy assignment and purge eligibility | `not_supported` | Retention model is not implemented yet. |
| Legal hold set/release with purge blocking | `not_supported` | Legal-hold model and APIs are not implemented yet. |
| Supersession, correction, and reissue relationships | `not_supported` | Lifecycle relationship model is not implemented yet. |
| Report-to-archive handoff | `not_supported` | `lotus-report` integration is not implemented yet. |
| Gateway-backed document retrieval | `not_supported` | Gateway facade is not implemented yet. |
| Workbench document retrieval surface | `not_supported` | Product surface is not implemented and must remain gateway-backed if added. |
| Arbitrary file storage | `not_supported` | Out of RFC-0103 scope. |
| Manual customer document upload | `not_supported` | Out of RFC-0103 first-wave scope. |

## Update Rule

Add a capability here only after the backing code, tests, documentation, and PR evidence exist. Do
not describe infrastructure as a client-supported retrieval feature.
