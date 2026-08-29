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
7. Structured support-safe route-template request logging.
8. Archive metadata model and PostgreSQL migration contract.
9. Explicit local-development runtime composition with in-memory metadata/audit repositories and
   filesystem-backed development storage behind the object-storage abstraction.
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
20. Archive-owned generated-document source events for downstream portfolio-memory consumers.
21. Report-to-archive handoff after successful PDF render through `lotus-report`.
22. Gateway-backed product retrieval through `lotus-gateway` archived document routes.
23. Gateway-backed Workbench archive retrieval through the `lotus-workbench` BFF and
    `lotus-gateway` archived document routes.
24. RFC-0108 archive supportability posture through `/metadata`
    `archive.observability.archive_supportability`.
25. Bounded archive supportability metric `lotus_archive_supportability_total` with only `state`,
    `reason`, and `freshness_bucket` labels.
26. Runtime build metadata through `/version` with source-safe commit, repository, Git ref, CI run
    id, image reference, image digest, and digest posture fields.
27. Governed `pip-audit` exception policy with owner, review date, rationale, dependency
    constraint, removal condition, and CI-backed validation; the release image also enforces a
    hard CRITICAL/HIGH vulnerability scan before signing or attestation.
28. Governed generated-report type validation for `portfolio_review`, `outcome_review`,
    `proof_pack`, and `rebalance_wave` archive records.
29. RFC-0023 reviewed advisory narrative archive summaries for rendered portfolio-review
    documents, preserving support-safe package lineage without raw narrative text.
30. RFC-0024 advisor proposal memo archive summaries for rendered portfolio-review documents,
    preserving support-safe memo lineage without raw memo reconstruction or client-ready promotion.
31. Limited Archive-owned Idea evidence lifecycle decisions with tenant enforcement, durable local
    idempotency, Ed25519 authentication, legal-hold precedence, and no disposal authority.
32. RFC-0002 reviewed Idea evidence-pack archive summaries for rendered proof-pack documents,
    preserving evidence ids, source-contract lineage, retention posture, source-event refs, and
    access-audit evidence without raw Idea evidence payloads or client-publication authority.
33. Bounded caller-scoped archive access preflight for `lotus-gateway`, with ordered per-document
    posture, tenant/region scope enforcement, partial/unavailable semantics, and no raw storage or
    archive payload exposure.
34. Production runtime composition with PostgreSQL document metadata, legal-hold, lifecycle and
    access-audit persistence plus checksum-evidenced, server-side-encrypted S3-compatible object
    storage.

The current local runtime is intentionally non-durable. Production-like profiles must not silently
use in-memory metadata/audit repositories or temporary filesystem object storage; they require the
PostgreSQL and S3 adapters plus their mandatory configuration.

Workbench-facing archive retrieval is supported only through the `lotus-workbench` BFF and
`lotus-gateway`. Workbench must not call `lotus-archive` directly.

## Supported Internal Capabilities

| Capability | Support state | Backing implementation |
| --- | --- | --- |
| Generated-document archival | `ready` | `POST /documents`, `ArchiveWriter`, metadata model, required tenant scope, storage adapter, checksum validation, and idempotency tests. Requests without a non-empty tenant are rejected before storage. |
| Controlled document metadata lookup | `ready` | `GET /documents/{document_id}` with caller-context enforcement, authorization, audit, and support-safe response model. |
| Controlled document binary download | `ready` | `GET /documents/{document_id}/download` with caller-context enforcement, authorization, storage retrieval, checksum verification, and audit. |
| Batch caller access preflight | `ready` | `POST /documents/access-preflight` evaluates up to 100 ordered document identifiers through one repository batch lookup and returns advisory `allowed`, `denied`, or `unavailable` posture with bounded reason codes. A denied item is deliberately identical for a non-existent identifier and an identifier outside the caller's tenant/region, so the response cannot be used as an existence oracle; granular reasons are recorded in the access audit only. It does not mint links or authorize downloads. |
| Access audit for archive API actions | `ready` | Local/test profiles use the in-memory repository; PostgreSQL mode persists the same event contract in `archive_access_audit`. `GET /documents/{document_id}/access-events` supports investigation without exposing raw payloads. |
| Retention policy posture | `ready` | `GET /documents/{document_id}/retention` returns source-backed retention fields, purge posture, legal-hold posture, authorization, and audit. |
| Purge eligibility and execution | `ready` | `POST /documents/{document_id}/purge-evaluation` and `POST /documents/{document_id}/purge` enforce retention expiry, support-safe reason codes, binary deletion through storage abstraction, idempotency after purge, and audit. |
| Legal hold set/release with purge blocking | `ready` | `POST /documents/{document_id}/legal-holds`, `DELETE /documents/{document_id}/legal-holds/{legal_hold_id}`, legal-hold repository model, migration contract, metadata summary refresh, purge blocking, and audit. |
| Supersession, correction, and reissue relationships | `ready` | `POST /documents/{document_id}/supersede`, `POST /documents/{document_id}/correct`, `POST /documents/{document_id}/reissue`, append-only lifecycle relationship records, current-document resolution, conflict checks, and audit. |
| Current document resolution | `ready` | `GET /documents/{document_id}/current` resolves supersession, correction, and reissue chains while preserving historical metadata lookup through `GET /documents/{document_id}`. |
| Archive document source events | `ready` | `GET /documents/{document_id}/source-events` projects archive-owned generated-document archive, supersession, correction, and client-delivery reissue lineage for downstream portfolio-memory consumers. The response is a bounded pull-only contract with `limit`/`offset`, stable event ids, stable lifecycle reason codes, report-input provenance, portfolio/report/render/archive refs, checksum-backed content hashes, retention/redaction/access/audit policy, and bounded artifact refs without raw document bytes, storage keys, raw report payloads, raw lifecycle reason text, or raw client references. |
| Report-to-archive handoff | `ready` | `lotus-report` hands successful PDF render artifacts and source-backed metadata to `POST /documents`, records `archiving` and `archived` ledger events, and maps archive validation, conflict, storage, and execution failures truthfully. This generic handoff supports portfolio-review, RFC-0042 outcome-review, RFC-0040 proof-pack, and RFC-0041 rebalance-wave report artifacts when `report_type` and source hashes are supplied by `lotus-report`. |
| Reviewed advisory narrative archive summary | `ready` | RFC-0023 portfolio-review artifacts may carry `reviewed_advisory_narrative` metadata when `lotus-report` archived a PDF that includes the rendered advisor-use narrative page. `lotus-archive` preserves package id, review id, approved advisor-use state, policy version, source hashes, guardrail posture, rendered-page evidence, and source-event artifact refs without raw narrative sections or client-ready promotion. |
| Advisor proposal memo archive summary | `ready` | RFC-0024 portfolio-review artifacts may carry `advisor_proposal_memo` metadata when `lotus-report` archives a PDF that includes the rendered advisor-use proposal memo package. `lotus-archive` preserves memo id, proposal/version id, review event, approved advisor-use posture, memo/source hashes, section counts, and source-event artifact refs without raw memo reconstruction or client-ready promotion. |
| Idea evidence-pack archive summary | `ready` | RFC-0002 proof-pack artifacts may carry `idea_evidence_pack` metadata when `lotus-report` archives a rendered `proof-pack` package sourced from reviewed `lotus-idea` evidence. `lotus-archive` preserves report evidence-pack id, conversion intent, candidate id, evidence packet id, source-contract version, evidence fingerprint, retention policy reference, source-event artifact refs, and access-audit evidence without raw Idea evidence payloads, Idea-owned archive authority, or client-publication authority. |
| Outcome-review report artifact archive lifecycle | `ready` | RFC-0042 outcome-review artifacts use the same generated-document metadata, checksum, retention, legal-hold, access-audit, purge, lifecycle, current-document, Gateway retrieval, and Workbench BFF retrieval posture as other Lotus-generated report documents. `lotus-archive` does not recompute outcome evidence; it stores and governs the artifact metadata supplied by `lotus-report`. |
| Proof-pack report artifact archive lifecycle | `ready` | RFC-0040 proof-pack report artifacts are accepted only as governed generated reports with `report_type=proof_pack`. They use the same checksum, retention, legal-hold, access-audit, purge, lifecycle, current-document, Gateway retrieval, and Workbench BFF retrieval posture as other Lotus-generated report documents. `lotus-archive` does not recompute proof-pack evidence; it stores and governs the artifact metadata supplied by `lotus-report`. |
| Rebalance-wave report artifact archive lifecycle | `ready` | RFC-0041 rebalance-wave artifacts are accepted only as governed generated reports with `report_type=rebalance_wave`. They use the same checksum, retention, legal-hold, access-audit, purge, lifecycle, current-document, Gateway retrieval, and Workbench BFF retrieval posture as other Lotus-generated report documents. `lotus-archive` does not recompute wave membership, proof-pack posture, source hashes, or wave events; it stores and governs the artifact metadata supplied by `lotus-report`. |
| Gateway-backed document retrieval | `ready` | `lotus-gateway` PR #150 exposes `/api/v1/documents/{document_id}` and `/api/v1/documents/{document_id}/download`, forwards caller context as `lotus-gateway`, preserves support-safe metadata and checksum headers, and keeps archive storage locations hidden. |
| Gateway-backed Workbench document retrieval | `ready` | `lotus-workbench` PR #126 retrieves archive metadata and binary downloads through `/api/bff/api/v1/documents/{document_id}` and `/api/bff/api/v1/documents/{document_id}/download`, preserving the Gateway boundary and binary response headers. |
| Archive supportability posture | `ready` | `/metadata` publishes `archive.observability.archive_supportability` from live checks of the composed metadata repository, object storage, and access-audit repository plus drain state. Capability flags derive from those checks; bounded repository, storage, and audit reasons make `unavailable` reachable without exposing infrastructure details. `lotus_archive_supportability_total` records the same state, reason, and freshness posture. The supported-feature catalogue remains a separate build-time declaration. |
| Runtime build metadata | `ready` | `/version` and `/metadata.build` expose source-safe service version, repository URL, commit SHA, Git ref, build timestamp, CI run id, image reference, image digest, and digest posture. Docker builds inject matching OCI labels and runtime environment variables. |
| Idea evidence lifecycle decision proof | `limited` | `POST /documents/{document_id}/idea-lifecycle-decisions` issues short-lived Ed25519-signed, tenant-bound projections for archived proof-pack records. SQLite replay/conflict, hold precedence, expiry/forgery rejection, audit, and failure atomicity are tested. Production durable persistence, managed keys/trust distribution, legal approval, and live mainline proof remain blocked. |
| Production durable archive runtime | `ready` | Runtime settings and `build_archive_service` align on PostgreSQL metadata/audit plus S3-compatible storage. Migration `007` persists access audit; adapter tests cover failure mapping and configuration, a PostgreSQL reconstruction integration test proves metadata and audit survive repository restart, and `/metadata` measures all three composed adapters. Deployment certification still requires operated migrations and managed credentials/keys. |
| Production container provenance certification | `limited` | The runtime image is wheel-based, non-root, contains only the application wheel and declared runtime dependencies, removes the package installer after installation, and carries OCI/runtime metadata. Mainline CI is configured for GHCR publication, immutable digest capture, hard CRITICAL/HIGH vulnerability scan, signature, provenance attestation, verification, and release evidence. Deployment certification still requires digest-based deployment manifests and same-digest promotion evidence. |
| Dependency vulnerability exceptions | `ready` | `make security-audit` validates `security/pip-audit-exceptions.json` before invoking `pip-audit`. The current policy has no active exceptions after the Starlette runtime was lifted to the fixed line. Future exceptions must carry owner, review date, rationale, dependency constraint, removal condition, and compensating controls. |

## Not Yet Supported

| Capability | Support state | Reason |
| --- | --- | --- |
| Direct Workbench archive calls | `not_supported` | Workbench retrieval must remain routed through the BFF and `lotus-gateway`; direct `lotus-archive` calls are outside the product boundary. |
| Unsupported report types | `not_supported` | Archive records are limited to governed Lotus-generated report types. Arbitrary `report_type` values are rejected instead of becoming undeclared product support. |
| Client-ready advisory narrative publication | `not_supported` | RFC-0023 archive support is advisor-use only. Client-ready commentary remains gated until Advise, Report, Render, Archive, Gateway, and Workbench client-ready controls are implemented and certified. |
| Arbitrary file storage | `not_supported` | Out of RFC-0103 scope. |
| Manual customer document upload | `not_supported` | Out of RFC-0103 first-wave scope. |

## Update Rule

Add a capability here only after the backing code, tests, documentation, and PR evidence exist. Do
not describe infrastructure as a client-supported retrieval feature.
