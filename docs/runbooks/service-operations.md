# Service Operations Runbook

## Current Support Posture

`lotus-archive` currently exposes scaffold and service-health behavior only. Do not use this service
for document archival, binary retrieval, legal hold, purge, retention, report handoff, gateway
retrieval, or Workbench retrieval until those capabilities are implemented and listed in
`docs/supported-features.md`.

## Standard Commands

- make lint
- make typecheck
- make ci
- docker compose up --build

## Health and Readiness

- Liveness: /health/live
- Readiness: /health/ready
- General health: /health
- Metadata: /metadata

## Incident First Checks

1. Check container logs for request failures and stack traces.
2. Verify /health/ready and metrics endpoint.
3. Run local parity check (make ci) before hotfix PR.

## Archive-Specific First Checks

When archive domain behavior is added, incident checks must preserve these boundaries:

1. confirm whether the issue is metadata, storage, audit, retention, legal hold, lifecycle, report
   handoff, or gateway retrieval;
2. do not inspect or expose document binary content while diagnosing service health;
3. use correlation identifiers and support-safe metadata rather than object keys or customer names;
4. distinguish render completion from archive completion.
