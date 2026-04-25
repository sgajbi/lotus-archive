# Service Operations Runbook

## Current Support Posture

`lotus-archive` currently exposes scaffold, service-health, safe error-envelope,
caller-context-parsing, correlation/trace propagation, metrics, structured request-log behavior,
metadata model, migration contract, storage adapter, checksum validation, archive-write domain
service behavior, internal archive create API, controlled metadata lookup, checksum-verified binary
download, and access-audit recording. Do not use this service for legal hold, purge, retention,
document lifecycle relationships, report handoff, gateway retrieval, or Workbench retrieval until
those capabilities are implemented and listed in `docs/supported-features.md`.

## Standard Commands

- make lint
- make typecheck
- make migration-gate
- make ci
- docker compose up --build

## Health and Readiness

- Liveness: /health/live
- Readiness: /health/ready
- General health: `/health`
- Metadata: `/metadata`
- Metrics: `/metrics`
- Correlation header: `X-Correlation-Id`
- Trace header: `X-Trace-Id`

## Incident First Checks

1. Check structured request logs for correlation ID, trace ID, method, path, status, and duration.
2. Verify `/health/ready` and metrics endpoint.
3. Run local parity check (make ci) before hotfix PR.

## Archive-Specific First Checks

When archive domain behavior is added, incident checks must preserve these boundaries:

1. confirm whether the issue is metadata, storage, audit, retention, legal hold, lifecycle, report
   handoff, or gateway retrieval;
2. do not inspect or expose document binary content while diagnosing service health;
3. use correlation identifiers and support-safe metadata rather than object keys or customer names;
4. distinguish render completion from archive completion.
5. verify caller context and authorization before treating archive reads as data loss.
6. verify checksum mismatch and missing-binary errors through support-safe error codes.
