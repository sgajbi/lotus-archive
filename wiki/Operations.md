# Operations

How to tell whether `lotus-archive` is healthy, what its posture surfaces do and do not mean, and
where the procedures live. The step-by-step checks are authored in the repository and linked below
rather than repeated here.

Current scope covers existing archive runtime controls and bounded v1/v2
Composite custody. Linked v3 has component/PostgreSQL upgrade proof; qualified
joined HTTP acceptance remains pending. Start with The surfaces for health,
Procedures for composition, and Composite v2 custody upgrade for migration
and recovery boundaries.

## The surfaces

| surface | answers |
|---|---|
| `GET /health/live` | is the process up? — nothing else |
| `GET /health/ready` | should this instance receive traffic? |
| `GET /metadata` | what was composed, which dependencies respond, and what can operate now? |
| `GET /metrics` | how much work, how fast, failing how? |
| `GET /version` | which build is this, and what provenance does it carry? |

### Readiness

`/health/ready` returns `503` in three cases: the instance is draining, `runtime_posture` reports
`unavailable`, or a composed dependency fails its live readiness probe. Otherwise it returns the
posture state and reason.

The posture states are:

| state | reason | meaning |
|---|---|---|
| `degraded` | `explicit_local_development_runtime` | a local or test profile with non-durable adapters |
| `unavailable` | `durable_archive_runtime_missing` | a non-local profile without durable metadata or storage |
| `ready` | `durable_archive_runtime_configured` | durable metadata **and** durable storage |

`ready` is reachable for the production PostgreSQL + S3 composition and is measured, not assumed:
after the configured posture passes, the route probes the composed repository, object storage, and
access-audit adapters and returns `503 unavailable` with the same bounded reason the `/metadata`
supportability block uses (`archive_repository_unavailable`, `archive_storage_unavailable`,
`archive_access_audit_unavailable`) when one fails. A configured-but-unreachable database therefore
takes the instance out of rotation instead of reporting `ready` from settings shape. Probe latency
is bounded by the configured connect and statement timeouts. `degraded` remains expected for local
and test profiles.

### Measured supportability

`/metadata` publishes an `archive.observability.archive_supportability` block with a state and
per-capability flags — `retrievalSupported`, `retentionSupported`, `accessAuditSupported` and so on.

The route resolves the same `ArchiveDocumentService` dependency used by the document APIs and
performs bounded checks of its three adapters:

| measured dependency | durable check | capability impact when unavailable |
|---|---|---|
| metadata repository | reads the `archive_documents` schema | retrieval, retention, legal hold, lifecycle, Gateway and Workbench retrieval |
| object storage | verifies S3 bucket access; local profiles verify filesystem access | retrieval, Gateway and Workbench retrieval |
| access-audit repository | reads the `archive_access_audit` schema | access audit |

An unavailable dependency produces `state: unavailable`, `freshnessBucket: unknown`, and one of
`archive_repository_unavailable`, `archive_storage_unavailable`, or
`archive_access_audit_unavailable`. Raw connection, bucket, storage-path, tenant, and document
details are not returned. Drain state remains `degraded` with
`archive_supportability_draining`. The `supportedArchiveFeatures` list is still a build-time
catalogue and is not used as a health signal.

## Metrics

Four families, all with bounded label values validated at startup:

| metric | records |
|---|---|
| `lotus_archive_operations_total` | archive operations by outcome |
| `lotus_archive_operation_duration_seconds` | operation latency |
| `lotus_archive_document_size_bytes` | archived document sizes |
| `lotus_archive_supportability_total` | supportability observations by `state`, `reason`, `freshness_bucket` |

Metric contracts are validated when the application starts, so a malformed metric fails the process
rather than shipping a broken series. Unknown label values fall back to a known value at the
recorder rather than creating an unbounded number of series.

`lotus_archive_supportability_total` records the same bounded state, reason, and freshness emitted
by `/metadata`, so operators can alert on a specific dependency class without introducing
high-cardinality infrastructure or customer identifiers.

## Reading the audit trail

`GET /documents/{document_id}/access-events` is the operational answer to "who touched this
document". It returns every recorded event for the document, including refusals — an
`authorization_denied` event carries the reason code for *why* the caller was refused, which is the
fastest way to distinguish a caller allow-list problem from a tenant scope mismatch, since the HTTP
response deliberately does not distinguish them.

Local profiles keep audit events in memory. Production PostgreSQL mode persists the same event
contract in `archive_access_audit`, indexed by document and creation time.

## Common situations

| symptom | first thing to check |
|---|---|
| caller gets `401 caller_context_missing` | the caller is not sending `x-caller-service` / `x-actor-type` / `x-actor-id` |
| caller gets `401 caller_scope_missing` | a scoped read without `x-tenant-id` / `x-region` |
| a retried write appears to "succeed twice" | expected: create, legal-hold set, lifecycle transitions, purge, and hold release all converge on the already-applied result for an identical retry — check the access event reason code (`legal_hold_already_active`, `lifecycle_transition_already_recorded`, `already_purged`) |
| caller gets `403` on reads that used to work | tenant or region mismatch, or the document was purged — check the access events for the reason code |
| every read of one historical document is refused | inspect the access event reason; `document_scope_unavailable` identifies incomplete scope on a historical or migrated record, while new writes require both tenant and region |
| purge refused | `purge-evaluation` returns the reason: hold active, no retention date, or retention still running |
| `409 document_checksum_mismatch` | stored bytes no longer match the recorded checksum — treat as an integrity incident, not a retry |
| readiness `503` | draining, a non-local profile that cannot compose a durable runtime, or a measured dependency outage — the reason names which dependency failed |
| metadata supportability `unavailable` | use the bounded reason to isolate repository, storage, or access-audit readiness before inspecting support-safe infrastructure diagnostics |

## Procedures

The ordered operational procedures are in the repository:

- [service operations runbook](https://github.com/sgajbi/lotus-archive/blob/main/docs/runbooks/service-operations.md)
  — standard commands, health and readiness, incident first checks, archive-specific first checks,
  container provenance checks, and Idea lifecycle decision key operations
- [archive service boundaries](https://github.com/sgajbi/lotus-archive/blob/main/docs/architecture/archive-service-boundaries.md)
  — ownership decisions across services, when a question is "whose is this?"

## Read next

1. [Configuration](Configuration) — the settings behind every posture value above
2. [Security and Controls](Security-and-Controls) — what the audit trail records
3. [Document Lifecycle](Document-Lifecycle) — why a purge was refused

## Composite v2 custody upgrade

Linked v3 adds pending migration 016 after 015, with strict linked request/window
pins on the existing custody path. Never replay historical 014 or 015 over v3
records; keep a compatible schema/reader and forward-fix. Populated legacy-row,
atomic historical replay refusal and fresh-process proof are documented in
[linked custody acceptance](https://github.com/sgajbi/lotus-archive/blob/main/docs/composite-linked-custody-acceptance.md).
Actual qualified joined v3 HTTP acceptance remains pending; completed v1/v2
acceptance does not establish it.

Apply pending migration 015 after 014 before enabling v2 admissions. Never replay
014 over retained v2 records. For rollback, stop new v2 admissions and keep the
compatible reader/schema; preserve all objects and source identities and
forward-fix the defect. The [custody contract](https://github.com/sgajbi/lotus-archive/blob/main/docs/composite-custody-contract.md)
documents exact identity, retry semantics, populated upgrade proof and commands.

The [v2 custody acceptance ledger](https://github.com/sgajbi/lotus-archive/blob/main/docs/composite-v2-custody-delivery-ledger.md)
records the single fresh R5 phase on qualified main `280f6d8`: actual restart retained
the same PostgreSQL, objects and schema, with independent pre/post HTTP readers.
The final native PostgreSQL dump and all three objects are retained and verified;
only the owned R5 HTTP/PG/anonymous volume were retired and absence checked.
Historical R2/R3/R4 evidence remains unchanged. This explicit development runtime
does not establish production migration operation, full restore certification or
official financial authority.
