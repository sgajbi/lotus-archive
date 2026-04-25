# Repository Engineering Context

## Repository Role

`lotus-archive` is a Lotus backend service.

## Business And Domain Responsibility

`lotus-archive` owns: Generated-document archive, retrieval, retention, legal hold, access audit, and document lifecycle service

## Current-State Summary

`lotus-archive` is scaffolded from platform automation and starts with the governed backend baseline:
FastAPI service shell, CI workflows, repo-native quality commands, Docker baseline, AGENTS
contract, repository engineering context, safe service-level error envelope, caller-context parsing
helper, structured request logging, archive metadata model, migration contract, storage adapter,
checksum validation, idempotent archive-write domain service, internal archive create API,
controlled metadata lookup, checksum-verified binary download, access-audit recording, and
retention posture lookup, purge eligibility and execution, legal-hold set/release with purge
blocking, and archive-specific module-family/documentation structure.

No lifecycle, report-handoff, gateway, or Workbench retrieval capability is supported yet.

## Architecture And Module Map

1. `src/app/main.py`: application entrypoint, health/readiness, metadata.
2. `src/app/archive/service_profile.py`: implementation posture, module families, and
   unsupported product-capability baseline.
3. `src/app/contracts/errors.py`: support-safe error envelope contract.
4. `src/app/security/caller_context.py`: caller-context parser for future protected archive APIs.
5. `src/app/archive/models.py`: archive document metadata contract.
6. `src/app/archive/storage.py`: object-storage protocol and filesystem development adapter.
7. `src/app/archive/repository.py`: archive document repository protocol and in-memory test
   implementation.
8. `src/app/archive/archive_writer.py`: checksum-backed idempotent archive-write domain service.
9. `src/app/archive/api.py`: archive create, metadata lookup, binary download, and access-event
   API router.
10. `src/app/archive/api_models.py`: support-safe archive API request and response models.
11. `src/app/archive/audit.py`: access-audit event model and repository protocol.
12. `src/app/archive/authorization.py`: first-wave archive caller authorization policy.
13. `src/app/archive/service.py`: archive API orchestration, retrieval-time checksum
   verification, retention posture, purge eligibility/execution, and legal-hold state changes.
14. `migrations/`: PostgreSQL metadata contract migrations.
15. `src/app/contracts/`: API and contract models.
16. `src/app/middleware/`: shared request middleware.
17. `tests/unit`, `tests/integration`, `tests/e2e`: test pyramid baseline.
18. `docs/architecture/`: archive service boundaries and structure.
19. `docs/supported-features.md`: implementation-backed support posture.
20. `docs/standards/`: repository standards placeholders to be replaced with service truth.

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

## Standards And RFCs That Govern This Repository

1. `lotus-platform/rfcs/RFC-0072-platform-wide-multi-lane-ci-validation-and-release-governance.md`
2. `lotus-platform/context/LOTUS-QUICKSTART-CONTEXT.md`
3. `lotus-platform/context/LOTUS-ENGINEERING-CONTEXT.md`
4. service-specific RFCs once implementation begins

## Known Constraints And Implementation Notes

1. this is the platform scaffold baseline plus RFC-0103 Slice 1 through Slice 4 internal archive
   structure and API support, not full RFC completeness,
2. standards placeholders in `docs/standards/` must be replaced with service truth as the service
   matures,
3. keep business role, naming, docs, and tests aligned with actual implemented scope,
4. do not claim archive product support until code, tests, documentation, and PR evidence exist.

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
