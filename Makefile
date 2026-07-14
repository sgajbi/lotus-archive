.PHONY: install lint monetary-float-guard typecheck openapi-gate migration-gate test test-unit test-integration test-e2e test-coverage coverage-gate security-audit check ci docker-build docker-release-build clean

VENV_DIR ?= .venv
SERVICE_VERSION ?= 0.1.0
IMAGE_NAME ?= backend-service
IMAGE_TAG ?= ci-test
IMAGE_FULL_TAG ?= $(IMAGE_NAME):$(IMAGE_TAG)
IMAGE_REGISTRY ?= ghcr.io
IMAGE_REPOSITORY ?= sgajbi/lotus-archive
RELEASE_IMAGE_NAME ?= $(IMAGE_REGISTRY)/$(IMAGE_REPOSITORY)
RELEASE_IMAGE_TAG ?= $(GIT_COMMIT_SHA)
RELEASE_METADATA_FILE ?= image-build-metadata.json
GIT_COMMIT_SHA ?= $(shell git rev-parse HEAD)
GIT_REPOSITORY_URL ?= https://github.com/sgajbi/lotus-archive
GIT_REF ?= local
BUILD_TIMESTAMP_UTC ?= local
CI_RUN_ID ?= local
IMAGE_DIGEST ?= not-published
DOCKER_BUILD_ARGS := --build-arg SERVICE_VERSION=$(SERVICE_VERSION) --build-arg GIT_COMMIT_SHA=$(GIT_COMMIT_SHA) --build-arg GIT_REPOSITORY_URL=$(GIT_REPOSITORY_URL) --build-arg GIT_REF=$(GIT_REF) --build-arg BUILD_TIMESTAMP_UTC=$(BUILD_TIMESTAMP_UTC) --build-arg CI_RUN_ID=$(CI_RUN_ID) --build-arg IMAGE_DIGEST=$(IMAGE_DIGEST)

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

check: lint typecheck openapi-gate migration-gate test

ci: lint typecheck openapi-gate migration-gate test-integration test-e2e test-coverage security-audit

docker-build:
	docker build $(DOCKER_BUILD_ARGS) -t $(IMAGE_FULL_TAG) -t backend-service:ci-test .

docker-release-build:
	docker buildx build $(DOCKER_BUILD_ARGS) --metadata-file $(RELEASE_METADATA_FILE) --provenance=true --sbom=true --push -t $(RELEASE_IMAGE_NAME):$(RELEASE_IMAGE_TAG) .

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.ruff_cache', '.mypy_cache']]; [pathlib.Path(p).unlink(missing_ok=True) for p in ['.coverage', '.coverage.unit', '.coverage.integration', '.coverage.e2e']]"
