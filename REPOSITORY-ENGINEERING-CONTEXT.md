# Repository Engineering Context

## Repository Role

`lotus-archive` is a Lotus backend service.

## Business And Domain Responsibility

`lotus-archive` owns: Generated-document archive, retrieval, retention, legal hold, access audit, and document lifecycle service

## Current-State Summary

`lotus-archive` is scaffolded from platform automation and starts with the governed backend baseline:
FastAPI service shell, CI workflows, repo-native quality commands, Docker baseline, AGENTS
contract, repository engineering context, safe service-level error envelope, caller-context parsing
helper, structured route-template request logging, archive metadata model, migration contract,
explicit runtime composition settings, storage adapter,
checksum validation, idempotent archive-write domain service, internal archive create API,
controlled metadata lookup, checksum-verified binary download, access-audit recording, and
retention posture lookup, purge eligibility and execution, legal-hold set/release with purge
blocking, lifecycle relationship APIs, current-document resolution, gateway-backed document
resolution, archive-owned generated-document source events for downstream portfolio-memory
consumers, gateway-backed document retrieval through `lotus-gateway`, Gateway-backed Workbench retrieval through the Workbench BFF,
report-to-archive handoff through `lotus-report`, and
archive-specific module-family/documentation structure. RFC-0040 proof-pack report artifacts and
RFC-0041 rebalance-wave report artifacts are now covered by the generated-document lifecycle when
`lotus-report` supplies governed `report_type=proof_pack` or `report_type=rebalance_wave`
metadata; arbitrary report types are rejected by the archive metadata contract. RFC-0023 reviewed
advisory narrative portfolio-review artifacts can now preserve a support-safe
`reviewed_advisory_narrative` archive summary when the PDF includes the rendered advisor-use
narrative page; raw narrative sections and client-ready promotion remain out of scope. RFC-0024
advisor proposal memo portfolio-review artifacts can now preserve a support-safe
`advisor_proposal_memo` archive summary when the PDF includes the rendered advisor-use memo page;
raw memo reconstruction and client-ready memo promotion remain out of scope. RFC-0002 reviewed Idea
evidence pack artifacts can now preserve a support-safe
`idea_evidence_pack` archive summary when `lotus-report` archives a rendered `proof-pack` package
sourced from `lotus-idea`; Archive preserves evidence ids, source-contract lineage, retention
posture, access-audit events, and source-event artifact refs without raw Idea evidence payloads or
client-publication authority. RFC-0108 archive supportability now publishes `archive.observability.archive_supportability` through `/metadata` and
`lotus_archive_supportability_total`, covering retrieval, retention, legal-hold, access-audit,
lifecycle, gateway retrieval, and Gateway-backed Workbench retrieval with bounded labels only.
Archive runtime build metadata is exposed through `src/app/archive/build_metadata.py`, `/version`,
and `/metadata.build`; Docker builds inject matching source-safe OCI labels and runtime environment
variables. Mainline CI is configured to publish the release image to GHCR, capture the immutable
digest, scan, sign, attest, verify, and write release evidence. Full production deployment
certification remains limited until deployment manifests consume the digest and same-digest
promotion evidence exists.

Workbench retrieval is supported only through the Workbench BFF and `lotus-gateway`; Workbench must
not call `lotus-archive` directly.

## Architecture And Module Map

1. `src/app/main.py`: application entrypoint, health/readiness, metadata.
2. `src/app/archive/service_profile.py`: implementation posture, module families, and
   unsupported product-capability baseline.
3. `src/app/contracts/errors.py`: support-safe error envelope contract.
4. `src/app/security/caller_context.py`: caller-context parser for future protected archive APIs.
5. `src/app/archive/models.py`: archive document metadata contract.
6. `src/app/archive/commands.py`: application-layer command inputs mapped from API DTOs.
7. `src/app/archive/storage.py`: object-storage protocol and filesystem development adapter.
8. `src/app/archive/repository.py`: archive document repository protocol and in-memory test
   implementation.
9. `src/app/archive/archive_writer.py`: checksum-backed idempotent archive-write domain service.
10. `src/app/archive/api.py`: archive create, metadata lookup, binary download, and access-event
   API router.
11. `src/app/archive/api_models.py`: support-safe archive API request and response models.
12. `src/app/archive/audit.py`: access-audit event model and repository protocol.
13. `src/app/archive/authorization.py`: first-wave archive caller authorization policy.
14. `src/app/archive/service.py`: archive API orchestration, retrieval-time checksum
   verification, retention posture, purge eligibility/execution, legal-hold state changes,
   lifecycle relationship mutation, and current-document resolution.
15. `src/app/archive/source_events.py`: bounded pull-only archive-owned generated-document and
   client-delivery lifecycle source-event projection for portfolio-memory consumers.
16. `migrations/`: PostgreSQL metadata contract migrations.
17. `src/app/contracts/`: API and contract models.
18. `src/app/middleware/`: shared request middleware.
19. `tests/unit`, `tests/integration`, `tests/e2e`: test pyramid baseline.
20. `docs/architecture/`: archive service boundaries and structure.
21. `docs/supported-features.md`: implementation-backed support posture.
22. `docs/standards/`: repository standards placeholders to be replaced with service truth.
23. `src/app/archive/metrics.py`: bounded archive operation, size, and supportability metrics.
24. `src/app/archive/settings.py`: typed runtime profile, repository, storage, namespace, database,
    and upload-size configuration.
25. `src/app/archive/runtime.py`: process-local archive dependency composition and runtime posture.
26. `src/app/archive/build_metadata.py`: source-safe runtime build, Git, CI, and image provenance
    metadata exposed through `/version` and `/metadata.build`.
27. `src/app/archive/idea_lifecycle_decisions/`: tenant-bound Archive lifecycle decision models,
    durable idempotency adapter, Ed25519 signing/verification, and application service.

## Runtime And Integration Boundaries

1. Runtime model: `python-fastapi`
2. Upstream dependencies:
   - lotus-report
   - lotus-render
3. Downstream consumers:
   - lotus-gateway
4. Important boundary rule: this scaffold does not establish domain authority beyond the explicit
   service contract added later by RFC or implementation work.

## Repo-Native Commands

1. install or bootstrap: `make install`
2. lint: `make lint`
3. typecheck: `make typecheck`
4. unit tests: `make test-unit`
5. integration or browser tests where applicable: `make test-integration`, `make test-e2e`
6. migration contract gate: `make migration-gate`
7. repo-native CI parity: `make check`, `make ci`

## Validation And CI Expectations

`lotus-archive` follows the standard Lotus backend lane model. Required baseline checks include lint,
typecheck, OpenAPI quality, unit/integration/e2e tests, coverage gate, security audit, and Docker
build validation.

Pull requests use rebase merge to preserve linear, non-squashed commit history. The PR auto-merge
workflow must request `--rebase`; merge commits and squash merges are disabled by repository policy.

## Standards And RFCs That Govern This Repository

1. `lotus-platform/rfcs/RFC-0072-platform-wide-multi-lane-ci-validation-and-release-governance.md`
2. `lotus-platform/context/LOTUS-QUICKSTART-CONTEXT.md`
3. `lotus-platform/context/LOTUS-ENGINEERING-CONTEXT.md`
4. service-specific RFCs once implementation begins

## Known Constraints And Implementation Notes

1. this is the platform scaffold baseline plus RFC-0103 internal archive API, report handoff,
   gateway retrieval support, and Gateway-backed Workbench retrieval support, not production
   certification or customer-facing document delivery,
2. standards placeholders in `docs/standards/` must be replaced with service truth as the service
   matures,
3. keep business role, naming, docs, and tests aligned with actual implemented scope,
4. do not claim archive product support until code, tests, documentation, and PR evidence exist.
5. supportability metrics must remain bounded to state, reason, and freshness bucket only; do not
   add document, report, render, storage, tenant, trace, or correlation labels.
6. in-memory metadata/audit repositories and filesystem object storage are allowed only for
   explicit local-development or test profiles. Production-like profiles must fail closed or report
   unavailable until durable metadata/audit and object-storage adapters exist.
7. request logs must use route templates rather than raw document or legal-hold paths.
8. FastAPI API models must stay at the router boundary. `ArchiveDocumentService` consumes
   application commands from `src/app/archive/commands.py`, not `api_models.py`.
9. Source events are bounded pull-only document-evidence projections. They must publish stable
   reason codes and report-input provenance, never raw lifecycle free text, storage keys, raw
   payloads, client references, transaction facts, position facts, or calculation/methodology
   authority.
10. Idea lifecycle decisions are read-only Archive projections. They may expose support-safe Idea
    correlation references but never grant hold management, purge execution, portfolio, client,
    report-payload, or document-content authority to `lotus-idea`.
11. Idea evidence-pack archive summaries are source-safe metadata on Archive-generated-document
    records. They require `report_type=proof_pack`, `template_id=proof-pack`,
    `report_data_contract_version=dpm_proof_pack_report_input.v1`, rendered-page evidence, SHA-256
    evidence fingerprint lineage, and `client_publication_authority_granted=false`.
12. Local SQLite decision persistence and local Ed25519 keys are implementation proof only.
    Production requires a durable Archive repository, managed private-key source and rotation,
    consumer trust bundle, and live evidence.
13. Local container builds may expose `image_digest_posture=not_published`. Do not claim production
    deployment certification until mainline release evidence is paired with digest-based deployment
    manifests and same-digest promotion evidence.

## Context Maintenance Rule

Update this document when:

1. repository ownership changes,
2. repo-native commands or CI gates change,
3. runtime or integration boundaries change,
4. dominant local implementation patterns change,
5. current-state rollout or product posture materially changes.

## Cross-Links

1. `lotus-platform/context/LOTUS-QUICKSTART-CONTEXT.md`
2. `lotus-platform/context/LOTUS-ENGINEERING-CONTEXT.md`
3. `lotus-platform/context/CONTEXT-REFERENCE-MAP.md`
