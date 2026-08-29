# Development and Testing

Running the service locally, the commands that matter, and what CI actually enforces — including
where it does not.

## Local setup

```powershell
make install
uvicorn app.main:app --reload --port 8320
docker compose up --build
```

No external dependency is needed for the default local profile; it uses the in-memory repository and
filesystem storage. Durable adapter integration tests require PostgreSQL and set
`LOTUS_ARCHIVE_TEST_DATABASE_URL`. See [Configuration](Configuration#what-can-actually-run).

Expect `/health/ready` to report `degraded` with reason `explicit_local_development_runtime`. That
is the correct local state, not a fault.

## Commands

| command | what it does |
|---|---|
| `make lint` | ruff check, ruff format check, and the monetary-float guard |
| `make typecheck` | mypy |
| `make openapi-gate` | OpenAPI contract quality |
| `make migration-gate` | migration contract validation |
| `make code-health-gates` | the four gates below, as one target |
| `make complexity-gate` | no rank D–F function; maximum cyclomatic complexity at or below the banked 17 |
| `make source-size-gate` | no module past the banked 914 lines |
| `make dead-code-gate` | no vulture finding at 80% confidence |
| `make dependency-hygiene-gate` | no deptry finding; direct imports must be declared dependencies |
| `make security-audit` | dependency vulnerability audit |
| `make check` | lint, typecheck, both gates, **unit tests only** |
| `make ci` | the above plus integration, e2e, coverage and security audit |
| `make docker-build` / `make docker-release-build` | container builds |
| `make release-evidence` | build provenance evidence |

Code-health baselines are banked at the measured tree with no headroom, and
`tests/unit/test_code_health_gates.py` asserts each threshold *equals* the measurement — an
improvement cannot go unbanked and a threshold cannot drift above the tree. The same tests prove
each gate can fail by running it one below its measured value, and all four run in every CI lane,
not only from `make check`.

`make test` is an alias for `make test-unit`, so `make check` does not exercise the integration or
e2e suites. Run `make ci` before opening a PR that touches the archive path.

## Test layout

| suite | scope |
|---|---|
| `tests/unit` | 29 modules — domain service, metadata model, writer, storage, repository, authorization, runtime composition, metrics, OpenAPI contract, migration contract, CI-gate liveness, release evidence, documentation posture |
| `tests/integration` | documents API, Idea lifecycle decision API, health, request logging |
| `tests/e2e` | smoke coverage of the full path |

Coverage is enforced at **99%** across the combined suites, computed from separately uploaded
coverage data rather than a single run.

Two test modules are worth knowing about before editing anything:

- **`tests/unit/test_architecture_boundaries.py`** enforces the module-family boundaries described in
  [Architecture](Architecture#module-families). Structure drift fails the build rather than
  accumulating.
- **`tests/unit/test_documentation_posture.py`** asserts specific content in `README.md`,
  `wiki/Home.md`, the runbook, `docs/supported-features.md` and the boundaries doc — including that
  the supported-features table does not overclaim direct Workbench access, and that the local
  refactoring playbook remains only a pointer to the canonical copy. Documentation changes to those
  five files are gated by a test, deliberately.

## What CI runs

Five workflows: feature lane, PR merge gate, main releasability, merged-PR main releasability, and
PR auto-merge. The validating lanes run:

```
pip check → make lint → make typecheck → make openapi-gate → make migration-gate → make security-audit
          → pytest (unit | integration | e2e, in parallel)
          → combined coverage --fail-under=99
          → make docker-build / docker-release-build → make release-evidence
```

### Migration-contract enforcement

`make migration-gate` runs `scripts/migration_gate.py` and is wired into both `make check` and
`make ci`. Feature, pull-request, and main releasability workflows also invoke it explicitly in the
same blocking job as the OpenAPI and security controls, so durable PostgreSQL schema drift cannot
pass by relying on a developer's local command. `tests/unit/test_ci_gate_liveness.py` derives every
blocking `*-gate` dependency from the Makefile and requires each validating workflow to execute it;
a newly advertised gate therefore fails CI until it is live.

## Image and supply chain

Both pull requests and mainline block on any fixable CRITICAL or HIGH vulnerability, with identical
severity and `ignore-unfixed` settings, so a pull request cannot pass a bar the release lane would
fail. The PR Docker job scans the image it builds; mainline additionally blocks signing and
attestation. Release images carry only the application wheel and declared runtime dependencies, with
the package installer removed after installation so vendored metadata cannot pollute the SBOM.

## Documentation changes

Repo-local `wiki/` is the authored source of truth; the GitHub wiki is only a publication target and
must never receive hand-edited content absent from repo source. Update `wiki/` in the same PR as the
change it describes, verify before merge and publish after, using
`lotus-platform/automation/Sync-RepoWikis.ps1`. The full rule is in
[`AGENTS.md`](https://github.com/sgajbi/lotus-archive/blob/main/AGENTS.md).

Links from a wiki page to a repository file must be **absolute GitHub URLs**. A `../docs/...`
relative link resolves in-repo and 404s on the published wiki, which is flat.

## Read next

1. [Architecture](Architecture) — the structure the boundary tests enforce
2. [Configuration](Configuration) — why local is the only runnable profile
3. [Operations](Operations) — what the running service reports
