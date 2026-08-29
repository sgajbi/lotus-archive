.PHONY: install lint monetary-float-guard typecheck openapi-gate migration-gate complexity-gate source-size-gate dead-code-gate dependency-hygiene-gate code-health-gates test test-unit test-integration test-e2e test-coverage coverage-gate security-audit check ci docker-build docker-release-build release-evidence clean

VENV_DIR ?= .venv
LOTUS_ARCHIVE_VERSION ?= 0.1.0
LOTUS_ARCHIVE_IMAGE_NAME ?= lotus-archive
LOTUS_ARCHIVE_IMAGE_TAG ?= ci-test
LOTUS_ARCHIVE_IMAGE_REF ?= $(LOTUS_ARCHIVE_IMAGE_NAME):$(LOTUS_ARCHIVE_IMAGE_TAG)
IMAGE_REGISTRY ?= ghcr.io
IMAGE_REPOSITORY ?= sgajbi/lotus-archive
RELEASE_IMAGE_NAME ?= $(IMAGE_REGISTRY)/$(IMAGE_REPOSITORY)
RELEASE_IMAGE_TAG ?= $(LOTUS_ARCHIVE_COMMIT_SHA)
RELEASE_METADATA_FILE ?= image-build-metadata.json
LOTUS_ARCHIVE_COMMIT_SHA ?= $(shell git rev-parse HEAD)
LOTUS_ARCHIVE_REPOSITORY_URL ?= https://github.com/sgajbi/lotus-archive
LOTUS_ARCHIVE_BUILD_REF ?= $(or $(GITHUB_REF),local)
LOTUS_ARCHIVE_BUILD_TIMESTAMP_UTC ?= local
LOTUS_ARCHIVE_CI_RUN_ID ?= $(or $(GITHUB_RUN_ID),local)
LOTUS_ARCHIVE_IMAGE_DIGEST ?= not-published
DOCKER_BUILD_ARGS := --pull --build-arg LOTUS_ARCHIVE_VERSION=$(LOTUS_ARCHIVE_VERSION) --build-arg LOTUS_ARCHIVE_COMMIT_SHA=$(LOTUS_ARCHIVE_COMMIT_SHA) --build-arg LOTUS_ARCHIVE_REPOSITORY_URL=$(LOTUS_ARCHIVE_REPOSITORY_URL) --build-arg LOTUS_ARCHIVE_BUILD_REF=$(LOTUS_ARCHIVE_BUILD_REF) --build-arg LOTUS_ARCHIVE_BUILD_TIMESTAMP_UTC=$(LOTUS_ARCHIVE_BUILD_TIMESTAMP_UTC) --build-arg LOTUS_ARCHIVE_CI_RUN_ID=$(LOTUS_ARCHIVE_CI_RUN_ID) --build-arg LOTUS_ARCHIVE_IMAGE_REF=$(LOTUS_ARCHIVE_IMAGE_REF) --build-arg LOTUS_ARCHIVE_IMAGE_DIGEST=$(LOTUS_ARCHIVE_IMAGE_DIGEST)

ifeq ($(OS),Windows_NT)
VENV_PYTHON := $(VENV_DIR)/Scripts/python.exe
else
VENV_PYTHON := $(VENV_DIR)/bin/python
endif

install:
	python -m venv $(VENV_DIR)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -e ".[dev]"

lint:
	$(VENV_PYTHON) -m ruff check .
	$(VENV_PYTHON) -m ruff format --check .
	$(MAKE) monetary-float-guard

monetary-float-guard:
	$(VENV_PYTHON) scripts/check_monetary_float_usage.py

typecheck:
	$(VENV_PYTHON) -m mypy --config-file mypy.ini

openapi-gate:
	$(VENV_PYTHON) scripts/openapi_quality_gate.py

migration-gate:
	$(VENV_PYTHON) scripts/migration_gate.py

test:
	$(MAKE) test-unit

test-unit:
	$(VENV_PYTHON) -m pytest tests/unit

test-integration:
	$(VENV_PYTHON) -m pytest tests/integration

test-e2e:
	$(VENV_PYTHON) -m pytest tests/e2e

test-coverage:
	COVERAGE_FILE=.coverage.unit $(VENV_PYTHON) -m pytest tests/unit --cov=src --cov-report=
	COVERAGE_FILE=.coverage.integration $(VENV_PYTHON) -m pytest tests/integration --cov=src --cov-report=
	COVERAGE_FILE=.coverage.e2e $(VENV_PYTHON) -m pytest tests/e2e --cov=src --cov-report=
	$(MAKE) coverage-gate

coverage-gate:
	$(VENV_PYTHON) scripts/coverage_gate.py

security-audit:
	$(VENV_PYTHON) scripts/security_audit.py

SOURCE_FILE_MAX_LINES ?= 914
MAX_CYCLOMATIC_COMPLEXITY ?= 18
MAX_HIGH_COMPLEXITY_FUNCTIONS ?= 0

complexity-gate:
	$(VENV_PYTHON) scripts/python_complexity_inventory.py --limit 20 --max-cc $(MAX_CYCLOMATIC_COMPLEXITY) --max-high-complexity $(MAX_HIGH_COMPLEXITY_FUNCTIONS)

source-size-gate:
	$(VENV_PYTHON) scripts/source_size_gate.py --max-lines=$(SOURCE_FILE_MAX_LINES)

dead-code-gate:
	$(VENV_PYTHON) scripts/dead_code_gate.py

dependency-hygiene-gate:
	$(VENV_PYTHON) -m deptry .

code-health-gates: complexity-gate source-size-gate dead-code-gate dependency-hygiene-gate

check: lint typecheck code-health-gates openapi-gate migration-gate test

ci: lint typecheck code-health-gates openapi-gate migration-gate test-integration test-e2e test-coverage security-audit

docker-build:
	docker build $(DOCKER_BUILD_ARGS) -t $(LOTUS_ARCHIVE_IMAGE_REF) .

docker-release-build:
	docker buildx build $(DOCKER_BUILD_ARGS) --metadata-file $(RELEASE_METADATA_FILE) --provenance=true --sbom=true --push -t $(RELEASE_IMAGE_NAME):$(RELEASE_IMAGE_TAG) .

release-evidence:
	$(VENV_PYTHON) scripts/generate_release_evidence.py --buildx-metadata $(RELEASE_METADATA_FILE) --output release-evidence.json

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.ruff_cache', '.mypy_cache']]; [pathlib.Path(p).unlink(missing_ok=True) for p in ['.coverage', '.coverage.unit', '.coverage.integration', '.coverage.e2e']]"
