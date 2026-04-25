# lotus-archive

Lotus generated-document archive, retrieval, retention, legal hold, and access audit service

## Current Posture

`lotus-archive` is the governed service boundary for generated Lotus reporting documents. It is not
a generic file store, manual upload service, customer delivery channel, or report-rendering service.

The current implementation supports the service scaffold, health/readiness, metadata, metrics,
correlation headers, quality gates, and archive-specific structure. Archive create, retrieval,
retention, purge, legal hold, lifecycle relationships, report handoff, gateway retrieval, and
Workbench retrieval are not supported yet.

## Quick Start

```powershell
make install
make lint
make typecheck
make openapi-gate
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
