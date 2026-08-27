# Development and Testing

Running the service locally, the commands that matter, and what CI actually enforces — including
where it does not.

## Local setup

```powershell
make install
uvicorn app.main:app --reload --port 8320
docker compose up --build
```

No external dependency is needed. The runnable configuration uses the in-memory repository and
filesystem storage, so the service starts with nothing behind it — which is also why it is not yet
deployable. See [Configuration](./Configuration.md#what-can-actually-run).

Expect `/health/ready` to report `degraded` with reason `explicit_local_development_runtime`. That
is the correct local state, not a fault.

## Commands

| command | what it does |
|---|---|
| `make lint` | ruff check, ruff format check, and the monetary-float guard |
| `make typecheck` | mypy |
| `make openapi-gate` | OpenAPI contract quality |
| `make migration-gate` | migration contract validation |
| `make security-audit` | dependency vulnerability audit |
| `make check` | lint, typecheck, both gates, **unit tests only** |
| `make ci` | the above plus integration, e2e, coverage and security audit |
| `make docker-build` / `make docker-release-build` | container builds |
| `make release-evidence` | build provenance evidence |

`make test` is an alias for `make test-unit`, so `make check` does not exercise the integration or
e2e suites. Run `make ci` before opening a PR that touches the archive path.

## Test layout

| suite | scope |
|---|---|
| `tests/unit` | 26 modules — domain service, metadata model, writer, storage, repository, authorization, runtime composition, metrics, OpenAPI contract, migration contract, release evidence, documentation posture |
| `tests/integration` | documents API, Idea lifecycle decision API, health, request logging |
| `tests/e2e` | smoke coverage of the full path |

Coverage is enforced at **99%** across the combined suites, computed from separately uploaded
coverage data rather than a single run.

Two test modules are worth knowing about before editing anything:

- **`tests/unit/test_architecture_boundaries.py`** enforces the module-family boundaries described in
  [Architecture](./Architecture.md#module-families). Structure drift fails the build rather than
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
pip check → make lint → make typecheck → make openapi-gate → make security-audit
          → pytest (unit | integration | e2e, in parallel)
          → combined coverage --fail-under=99
          → make docker-build / docker-release-build → make release-evidence
```

### The hole: the migration gate never runs

`make migration-gate` runs `scripts/migration_gate.py` and is wired into both `make check` and
`make ci`. **No workflow invokes any of those three targets** — every lane calls individual targets,
and `migration-gate` is not among them. The string `migration` does not appear anywhere in
`.github/workflows/`.

The migration contract protects the PostgreSQL schema the durable path depends on. It is validated
only when a developer runs `make check` locally. Tracked as
[#92](https://github.com/sgajbi/lotus-archive/issues/92).

This is worth stating plainly because a gate that is configured, correct and never executed reads
exactly like a passing one.

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

1. [Architecture](./Architecture.md) — the structure the boundary tests enforce
2. [Configuration](./Configuration.md) — why local is the only runnable profile
3. [Operations](./Operations.md) — what the running service reports
