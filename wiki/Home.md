# lotus-archive Wiki

Lotus generated-document archive, retrieval, retention, legal hold, and access audit service

## Current posture

- Governed service boundary scaffold is in place.
- Health, readiness, metadata, metrics, correlation/trace headers, safe error envelopes, structured
  request logging, metadata model, migration contract, filesystem-backed development storage,
  checksum validation, idempotent archive-write domain behavior, internal archive create API,
  controlled metadata lookup, checksum-verified binary download, access-audit recording, retention
  posture lookup, purge eligibility and execution, and legal-hold set/release with purge blocking
  are available.
- Lifecycle relationship APIs for supersession, correction, reissue, and current-document
  resolution are available.
- Report-to-archive handoff after successful PDF render is available through `lotus-report`.
- `/metadata` publishes RFC-0108 `archive.observability.archive_supportability` posture covering
  retrieval, retention, legal hold, access audit, lifecycle, gateway retrieval, and Gateway-backed
  Workbench retrieval.
- `lotus_archive_supportability_total` is implementation-backed with bounded `state`, `reason`,
  and `freshness_bucket` labels only, with recorder-level fallback for unknown label values.
- Workbench retrieval is supported only through the Workbench BFF and `lotus-gateway`; Workbench
  must not call `lotus-archive` directly.
- This service is limited to Lotus-generated document archive scope. It is not a generic file store
  or manual upload service.
- Wiki source lives in-repo and must be published through lotus-platform automation.

## Operator links

- `README.md`
- `docs/architecture/archive-service-boundaries.md`
- `docs/supported-features.md`
- `docs/runbooks/service-operations.md`
