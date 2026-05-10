# lotus-archive

Lotus generated-document archive, retrieval, retention, legal hold, and access audit service

## Current Posture

`lotus-archive` is the governed service boundary for generated Lotus reporting documents. It is not
a generic file store, manual upload service, customer delivery channel, or report-rendering service.

The current implementation supports the service scaffold, health/readiness, metadata, metrics,
correlation, trace, and `traceparent` headers, structured request logging, safe error envelopes, caller-context
parsing, archive metadata model, migration contract, filesystem-backed development storage adapter,
checksum validation, idempotent archive-write domain service, archive create API, controlled
metadata lookup, controlled binary download, access-audit recording for archive API actions,
retention posture lookup, purge eligibility and execution, legal-hold set/release with purge
blocking, lifecycle relationship APIs for supersession/correction/reissue, current-document
resolution, archive-owned generated-document source events for downstream portfolio-memory
consumers, report-to-archive handoff after successful PDF render, governed report-type
validation for portfolio-review, outcome-review, proof-pack, and rebalance-wave artifacts, quality gates,
archive-specific structure, gateway-backed document retrieval, and Gateway-backed Workbench archive
retrieval. Product retrieval must flow through `lotus-gateway`; Workbench must not call
`lotus-archive` directly.

RFC-0040 proof-pack report artifacts are supported when `lotus-report` supplies source-backed
metadata with `report_type=proof_pack`, the `proof-pack` render template, and
`dpm_proof_pack_report_input.v1` lineage. `lotus-archive` stores and governs the generated
artifact; it does not recompute proof-pack evidence, source hashes, or report sections.

RFC-0041 rebalance-wave report artifacts are supported when `lotus-report` supplies source-backed
metadata with `report_type=rebalance_wave`, the `rebalance-wave` render template, and
`dpm_wave_report_input.v1` lineage. `lotus-archive` stores and governs the generated artifact; it
does not recompute wave membership, proof-pack posture, source hashes, or wave events.

RFC-0108 archive supportability posture is published through `/metadata` as
`archive.observability.archive_supportability` and counted through bounded
`lotus_archive_supportability_total` observations. The posture covers retrieval, retention,
legal-hold, access-audit, lifecycle, gateway retrieval, and Gateway-backed Workbench retrieval
without document, storage, report, render, tenant, trace, or correlation labels.

`GET /documents/{document_id}/source-events` exposes the archive-owned
`lotus-archive.generated_document_client_communication.v1` source-event family for downstream
portfolio-memory consumers. It projects generated-document archive, supersession, correction, and
client-delivery reissue lineage with portfolio/report/render/archive refs and checksum-backed
hashes, but never raw document bytes, storage keys, raw report payloads, or raw client references.

## Quick Start

```powershell
make install
make lint
make typecheck
make openapi-gate
make migration-gate
make check
make ci
```

```powershell
.venv\\Scripts\\python.exe -m pip install -e '.[dev]'
.venv\\Scripts\\python.exe -m ruff check . && .venv\\Scripts\\python.exe -m ruff format --check .
.venv\\Scripts\\python.exe -m mypy --config-file mypy.ini
.venv\\Scripts\\python.exe scripts/openapi_quality_gate.py
.venv\\Scripts\\python.exe -m pytest tests/unit tests/integration tests/e2e
.venv\\Scripts\\python.exe scripts/coverage_gate.py
```

## Run

```powershell
uvicorn app.main:app --reload --port 8150
```

## Docker

```powershell
docker compose up --build
```

## Standards

- CI and governance: .github/workflows/
- Engineering commands: Makefile
- Platform standards docs: docs/standards/
- Archive boundaries: docs/architecture/archive-service-boundaries.md
- Supported feature posture: docs/supported-features.md
