.PHONY: help install dev setup uninstall run daemon test test-all lint doctor status logs clean sample docs

PYTHON := python3
UV     := uv
UNIT   := app-com.watkinslabs.Dictator.service

help: ## Show this help
	@echo "dictator v2 — headless dictation service"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[32m%-14s\033[0m %s\n", $$1, $$2}'
	@echo ""

install: ## Install the package into the project environment
	$(UV) sync

dev: ## Install with test and development extras
	$(UV) sync --all-extras
	$(UV) pip install pytest pytest-asyncio

setup: install ## Install the systemd unit and desktop entry, then start the service
	$(UV) run dictator setup --install

uninstall: ## Stop the service and remove the unit and desktop entry
	-$(UV) run dictator setup --uninstall

daemon: ## Run the daemon in this terminal (debug logging)
	$(UV) run dictatord --log-level debug

run: daemon ## Alias for 'daemon'

test: ## Run the test suite
	$(UV) run pytest -q

test-all: ## Run every test, including the slow ones
	$(UV) run pytest -q -m ""

doctor: ## Check every dependency and report what to fix
	-$(UV) run dictator doctor

status: ## Show what the daemon is doing
	-$(UV) run dictator status

logs: ## Follow the service log
	journalctl --user -u $(UNIT) -f -o cat

docs: ## Regenerate the reference pages that are produced from code
	$(UV) run python scripts/gen_docs.py

sample: ## Print a fully commented configuration file
	$(UV) run dictator config sample

lint: ## Byte-compile everything as a syntax check
	$(UV) run python -m compileall -q dictatord dictator_cli

clean: ## Remove build artefacts and caches
	rm -rf build dist *.egg-info .pytest_cache htmlcov .coverage
	find . -path ./.venv -prune -o -name __pycache__ -type d -print0 2>/dev/null | xargs -0 rm -rf
