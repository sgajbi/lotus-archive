# Operations

How to tell whether `lotus-archive` is healthy, what its posture surfaces do and do not mean, and
where the procedures live. The step-by-step checks are authored in the repository and linked below
rather than repeated here.

## The surfaces

| surface | answers |
|---|---|
| `GET /health/live` | is the process up? — nothing else |
| `GET /health/ready` | should this instance receive traffic? |
| `GET /metadata` | what was composed, and what does the service claim to support? |
| `GET /metrics` | how much work, how fast, failing how? |
| `GET /version` | which build is this, and what provenance does it carry? |

### Readiness

`/health/ready` returns `503` in two cases: the instance is draining, or `runtime_posture` reports
`unavailable`. Otherwise it returns the posture state and reason.

The posture states are:

| state | reason | meaning |
|---|---|---|
| `degraded` | `explicit_local_development_runtime` | a local or test profile with non-durable adapters — **the normal state today** |
| `unavailable` | `durable_archive_runtime_missing` | a non-local profile without durable metadata or storage |
| `ready` | `durable_archive_runtime_configured` | durable metadata **and** durable storage |

`ready` is currently unreachable: it requires adapters that do not exist, and the settings validator
rejects the profiles that would ask for them
([#90](https://github.com/sgajbi/lotus-archive/issues/90)). A healthy instance today reports
`degraded`. Do not treat `degraded` as an incident signal in a local or test deployment; do treat it
as the reason this service is not yet deployable.

### Supportability is declared, not measured

`/metadata` publishes an `archive.observability.archive_supportability` block with a state and
per-capability flags — `retrievalSupported`, `retentionSupported`, `accessAuditSupported` and so on.

**Only drain state is measured.** Every capability flag is a literal `true`, and the `unavailable`
state is unreachable because it is gated on an empty feature list that is a non-empty module
constant. The block records that the features were built, not that they work
([#91](https://github.com/sgajbi/lotus-archive/issues/91)).

Practically: `state: ready` and `accessAuditSupported: true` on this surface tell you nothing about
whether the repository or storage is reachable. `/health/ready` is the surface that reflects the
composed runtime. Use it, not the supportability block, to decide whether to route traffic.

The same block also publishes `runtimePosture` — the profile, the adapter modes and the durability
booleans — which *is* derived from settings, with the caveat that `durable_audit` is derived from
`repository_mode` rather than from the audit repository in use.

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

Because supportability is static, `lotus_archive_supportability_total` will only ever record `ready`
or `draining`. An alert on `state="unavailable"` from this metric can never fire.

## Reading the audit trail

`GET /documents/{document_id}/access-events` is the operational answer to "who touched this
document". It returns every recorded event for the document, including refusals — an
`authorization_denied` event carries the reason code for *why* the caller was refused, which is the
fastest way to distinguish a caller allow-list problem from a tenant scope mismatch, since the HTTP
response deliberately does not distinguish them.

Remember that the audit repository is in-memory: events are lost on restart, so this is a live
investigation tool today rather than a durable record
([#90](https://github.com/sgajbi/lotus-archive/issues/90)).

## Common situations

| symptom | first thing to check |
|---|---|
| caller gets `401 caller_context_missing` | the caller is not sending `x-caller-service` / `x-actor-type` / `x-actor-id` |
| caller gets `401 caller_scope_missing` | a scoped read without `x-tenant-id` / `x-region` |
| caller gets `403` on reads that used to work | tenant or region mismatch, or the document was purged — check the access events for the reason code |
| every read of one document is refused | the document may have been archived without a `tenant_id` and is permanently unreadable ([#93](https://github.com/sgajbi/lotus-archive/issues/93)) |
| purge refused | `purge-evaluation` returns the reason: hold active, no retention date, or retention still running |
| `409 document_checksum_mismatch` | stored bytes no longer match the recorded checksum — treat as an integrity incident, not a retry |
| readiness `503` | draining, or a non-local profile that cannot compose a durable runtime |

## Procedures

The ordered operational procedures are in the repository:

- [service operations runbook](https://github.com/sgajbi/lotus-archive/blob/main/docs/runbooks/service-operations.md)
  — standard commands, health and readiness, incident first checks, archive-specific first checks,
  container provenance checks, and Idea lifecycle decision key operations
- [archive service boundaries](https://github.com/sgajbi/lotus-archive/blob/main/docs/architecture/archive-service-boundaries.md)
  — ownership decisions across services, when a question is "whose is this?"

## Read next

1. [Configuration](./Configuration.md) — the settings behind every posture value above
2. [Security and Controls](./Security-and-Controls.md) — what the audit trail records
3. [Document Lifecycle](./Document-Lifecycle.md) — why a purge was refused
