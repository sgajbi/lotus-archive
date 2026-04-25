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
- Workbench retrieval is not supported yet.
- Product retrieval is supported only through `lotus-gateway`; Workbench must not call
  `lotus-archive` directly.
- This service is limited to Lotus-generated document archive scope. It is not a generic file store
  or manual upload service.
- Wiki source lives in-repo and must be published through lotus-platform automation.

## Operator links

- `README.md`
- `docs/architecture/archive-service-boundaries.md`
- `docs/supported-features.md`
- `docs/runbooks/service-operations.md`
