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
16. Retention posture lookup for archived generated documents.
17. Purge eligibility evaluation and governed purge execution after retention expiry.
18. Legal-hold set/release with purge blocking and audit events.
19. Supersession, correction, and reissue relationships with current-document resolution.
20. Report-to-archive handoff after successful PDF render through `lotus-report`.
21. Gateway-backed product retrieval through `lotus-gateway` archived document routes.
22. Gateway-backed Workbench archive retrieval through the `lotus-workbench` BFF and
    `lotus-gateway` archived document routes.
23. RFC-0108 archive supportability posture through `/metadata`
    `archive.observability.archive_supportability`.
24. Bounded archive supportability metric `lotus_archive_supportability_total` with only `state`,
    `reason`, and `freshness_bucket` labels.
25. Governed generated-report type validation for `portfolio_review`, `outcome_review`, and
    `proof_pack` archive records.

Workbench-facing archive retrieval is supported only through the `lotus-workbench` BFF and
`lotus-gateway`. Workbench must not call `lotus-archive` directly.

## Supported Internal Capabilities

| Capability | Support state | Backing implementation |
| --- | --- | --- |
| Generated-document archival | `ready` | `POST /documents`, `ArchiveWriter`, metadata model, storage adapter, checksum validation, and idempotency tests. |
| Controlled document metadata lookup | `ready` | `GET /documents/{document_id}` with caller-context enforcement, authorization, audit, and support-safe response model. |
| Controlled document binary download | `ready` | `GET /documents/{document_id}/download` with caller-context enforcement, authorization, storage retrieval, checksum verification, and audit. |
| Access audit for archive API actions | `ready` | In-memory first-wave access-audit repository and `GET /documents/{document_id}/access-events` for support investigation. |
| Retention policy posture | `ready` | `GET /documents/{document_id}/retention` returns source-backed retention fields, purge posture, legal-hold posture, authorization, and audit. |
| Purge eligibility and execution | `ready` | `POST /documents/{document_id}/purge-evaluation` and `POST /documents/{document_id}/purge` enforce retention expiry, support-safe reason codes, binary deletion through storage abstraction, idempotency after purge, and audit. |
| Legal hold set/release with purge blocking | `ready` | `POST /documents/{document_id}/legal-holds`, `DELETE /documents/{document_id}/legal-holds/{legal_hold_id}`, legal-hold repository model, migration contract, metadata summary refresh, purge blocking, and audit. |
| Supersession, correction, and reissue relationships | `ready` | `POST /documents/{document_id}/supersede`, `POST /documents/{document_id}/correct`, `POST /documents/{document_id}/reissue`, append-only lifecycle relationship records, current-document resolution, conflict checks, and audit. |
| Current document resolution | `ready` | `GET /documents/{document_id}/current` resolves supersession, correction, and reissue chains while preserving historical metadata lookup through `GET /documents/{document_id}`. |
| Report-to-archive handoff | `ready` | `lotus-report` hands successful PDF render artifacts and source-backed metadata to `POST /documents`, records `archiving` and `archived` ledger events, and maps archive validation, conflict, storage, and execution failures truthfully. This generic handoff supports portfolio-review and RFC-0042 outcome-review report artifacts when `report_type` and source hashes are supplied by `lotus-report`. |
| Outcome-review report artifact archive lifecycle | `ready` | RFC-0042 outcome-review artifacts use the same generated-document metadata, checksum, retention, legal-hold, access-audit, purge, lifecycle, current-document, Gateway retrieval, and Workbench BFF retrieval posture as other Lotus-generated report documents. `lotus-archive` does not recompute outcome evidence; it stores and governs the artifact metadata supplied by `lotus-report`. |
| Proof-pack report artifact archive lifecycle | `ready` | RFC-0040 proof-pack report artifacts are accepted only as governed generated reports with `report_type=proof_pack`. They use the same checksum, retention, legal-hold, access-audit, purge, lifecycle, current-document, Gateway retrieval, and Workbench BFF retrieval posture as other Lotus-generated report documents. `lotus-archive` does not recompute proof-pack evidence; it stores and governs the artifact metadata supplied by `lotus-report`. |
| Gateway-backed document retrieval | `ready` | `lotus-gateway` PR #150 exposes `/api/v1/documents/{document_id}` and `/api/v1/documents/{document_id}/download`, forwards caller context as `lotus-gateway`, preserves support-safe metadata and checksum headers, and keeps archive storage locations hidden. |
| Gateway-backed Workbench document retrieval | `ready` | `lotus-workbench` PR #126 retrieves archive metadata and binary downloads through `/api/bff/api/v1/documents/{document_id}` and `/api/bff/api/v1/documents/{document_id}/download`, preserving the Gateway boundary and binary response headers. |
| Archive supportability posture | `ready` | `/metadata` publishes `archive.observability.archive_supportability`, sourced from supported archive feature posture and drain state, with bounded `lotus_archive_supportability_total` metric observations. |

## Not Yet Supported

| Capability | Support state | Reason |
| --- | --- | --- |
| Direct Workbench archive calls | `not_supported` | Workbench retrieval must remain routed through the BFF and `lotus-gateway`; direct `lotus-archive` calls are outside the product boundary. |
| Unsupported report types | `not_supported` | Archive records are limited to governed Lotus-generated report types. Arbitrary `report_type` values are rejected instead of becoming undeclared product support. |
| Arbitrary file storage | `not_supported` | Out of RFC-0103 scope. |
| Manual customer document upload | `not_supported` | Out of RFC-0103 first-wave scope. |

## Update Rule

Add a capability here only after the backing code, tests, documentation, and PR evidence exist. Do
not describe infrastructure as a client-supported retrieval feature.
