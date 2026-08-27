# lotus-archive

The system of record for documents the Lotus platform has generated. Once `lotus-report` has
assembled a client document and `lotus-render` has compiled it, `lotus-archive` holds custody: what
was produced, from what evidence, who has looked at it, and whether it may be destroyed yet.

It is not a general file store, a manual upload service, a delivery channel, or a renderer.

> **Status: not deployable.** No production configuration can currently start — the settings
> validator and the runtime composer accept disjoint configurations, because the PostgreSQL and S3
> adapters are not implemented. In the one runnable profile, document bytes sit on a local
> filesystem path and access audit is in-memory. See
> [#90](https://github.com/sgajbi/lotus-archive/issues/90). The domain behaviour below is
> implemented and tested; the durability it assumes is not.

**Documentation lives in the [wiki](https://github.com/sgajbi/lotus-archive/wiki)**, authored in
[`wiki/`](wiki/):

| page | for |
|---|---|
| [Home](https://github.com/sgajbi/lotus-archive/wiki/Home) | what the service is for, what it accepts, what it does not own |
| [Architecture](https://github.com/sgajbi/lotus-archive/wiki/Architecture) | module families, runtime composition, what is in memory |
| [API Surface](https://github.com/sgajbi/lotus-archive/wiki/API-Surface) | all 22 operations, the archive contract, error codes |
| [Document Lifecycle](https://github.com/sgajbi/lotus-archive/wiki/Document-Lifecycle) | retention, legal hold, purge, supersession, source events |
| [Security and Controls](https://github.com/sgajbi/lotus-archive/wiki/Security-and-Controls) | caller identity, tenant scope, audit, checksums |
| [Configuration](https://github.com/sgajbi/lotus-archive/wiki/Configuration) | every setting, and which combinations actually run |
| [Operations](https://github.com/sgajbi/lotus-archive/wiki/Operations) | readiness, posture, metrics, common situations |
| [Development and Testing](https://github.com/sgajbi/lotus-archive/wiki/Development-and-Testing) | building, testing, gates |

## Quick start

```powershell
make install
uvicorn app.main:app --reload --port 8320
```

Nothing external is required. `/health/ready` reports `degraded` with reason
`explicit_local_development_runtime` — that is the correct local state.

## Validate a change

```powershell
make check   # lint, typecheck, openapi + migration gates, unit tests
make ci      # the above plus integration, e2e, coverage and security audit
```

`make check` runs unit tests only. Note that CI does not currently invoke the migration gate
([#92](https://github.com/sgajbi/lotus-archive/issues/92)).

## Scope

`lotus-archive` accepts only Lotus-generated report documents of four governed types —
`portfolio_review`, `outcome_review`, `proof_pack` and `rebalance_wave` — submitted by
`lotus-report` after a successful PDF render. Report-to-archive handoff through `lotus-report` is
the only write path.

Product retrieval flows through `lotus-gateway`; Workbench retrieval is supported only through the
Workbench BFF and the Gateway route, and Workbench must not call `lotus-archive` directly.

`GET /documents/{document_id}/source-events` publishes a pull-only, bounded projection of
archive-owned generated-document and client-delivery lifecycle evidence for downstream
portfolio-memory consumers. It preserves report-input provenance and stable reason codes, and omits
document bytes, storage keys, raw report payloads, raw lifecycle reason text and raw client
references. The client-communication contract identifier is
`lotus-archive.generated_document_client_communication.v1`.

`POST /documents/{document_id}/idea-lifecycle-decisions` is a limited, **not-certified** Archive
producer boundary for Idea-linked proof-pack evidence: tenant-bound, short-lived Ed25519-signed
projections of retention, hold and purge posture with durable local replay protection. Decisions
never authorise disposal. Managed keys, durable production persistence, consumer trust distribution
and legal approval remain blockers ([#55](https://github.com/sgajbi/lotus-archive/issues/55)).

## Repository documentation

Deep reference material that belongs next to the code:

- [`docs/architecture/archive-service-boundaries.md`](docs/architecture/archive-service-boundaries.md)
  — cross-service ownership decisions and the module-family contract
- [`docs/supported-features.md`](docs/supported-features.md) — implementation-backed support posture
  per capability
- [`docs/runbooks/service-operations.md`](docs/runbooks/service-operations.md) — standard commands,
  incident first checks, container provenance, key operations
- [`docs/standards/`](docs/standards/) — platform standards this service is held to
- [`AGENTS.md`](AGENTS.md) and [`REPOSITORY-ENGINEERING-CONTEXT.md`](REPOSITORY-ENGINEERING-CONTEXT.md)
  — delivery posture, explicit runtime composition settings, and repository engineering context

## Known gaps

| gap | tracked |
|---|---|
| no durable adapters; no production profile can start | [#90](https://github.com/sgajbi/lotus-archive/issues/90) |
| `/metadata` supportability is declared, not measured | [#91](https://github.com/sgajbi/lotus-archive/issues/91) |
| migration gate never runs in CI | [#92](https://github.com/sgajbi/lotus-archive/issues/92) |
| `tenant_id` optional on write, required on read | [#93](https://github.com/sgajbi/lotus-archive/issues/93) |
| Idea lifecycle decisions not certified | [#55](https://github.com/sgajbi/lotus-archive/issues/55) |
