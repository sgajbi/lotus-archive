.PHONY: install lint monetary-float-guard typecheck openapi-gate test test-unit test-integration test-e2e test-coverage coverage-gate security-audit check ci docker-build clean

VENV_DIR ?= .venv

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
	$(VENV_PYTHON) -m pip_audit

check: lint typecheck openapi-gate test

ci: lint typecheck openapi-gate test-integration test-e2e test-coverage security-audit

docker-build:
	docker build -t backend-service:ci-test .

clean:
	python -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.ruff_cache', '.mypy_cache']]; [pathlib.Path(p).unlink(missing_ok=True) for p in ['.coverage', '.coverage.unit', '.coverage.integration', '.coverage.e2e']]"


