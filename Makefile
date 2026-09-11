.DEFAULT_GOAL := help
PY ?= python

.PHONY: help install dev lint fmt test run-hub run-sensor demo clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the package (runtime only)
	$(PY) -m pip install -e .

dev: ## Install with dev + sensor extras
	$(PY) -m pip install -e ".[dev,sensor]"

lint: ## ruff check + format check
	ruff check .
	ruff format --check .

fmt: ## Auto-format
	ruff check --fix .
	ruff format .

test: ## Run the test suite
	pytest

run-hub: ## Run the hub locally
	NETSENTINEL_ROLE=hub netsentinel hub --reload

run-sensor: ## Run the sensor locally (needs sudo for capture)
	NETSENTINEL_ROLE=sensor netsentinel sensor

demo: ## Bring up the docker compose demo stack
	docker compose up --build

clean: ## Remove caches and build artefacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info var
	find . -name __pycache__ -type d -exec rm -rf {} +
