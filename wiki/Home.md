# lotus-archive Wiki

Lotus generated-document archive, retrieval, retention, legal hold, and access audit service

## Current posture

- Governed service boundary scaffold is in place.
- Health, readiness, metadata, metrics, correlation/trace headers, safe error envelopes, and
  structured request logging are available.
- Archive create, retrieval, retention, purge, legal hold, lifecycle relationships, report handoff,
  gateway retrieval, and Workbench retrieval are not supported yet.
- This service is limited to Lotus-generated document archive scope. It is not a generic file store
  or manual upload service.
- Wiki source lives in-repo and must be published through lotus-platform automation.

## Operator links

- `README.md`
- `docs/architecture/archive-service-boundaries.md`
- `docs/supported-features.md`
- `docs/runbooks/service-operations.md`
