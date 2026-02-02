.PHONY: help install install-dev install-system uninstall uninstall-system run sync build clean test permissions update-desktop

# Variables
PYTHON := python3
UV := uv
PROJECT_NAME := the-dictator
SRC_DIR := src
DESKTOP_DIR := desktop
SCRIPTS_DIR := scripts

# Colors for output
BOLD := \033[1m
GREEN := \033[32m
YELLOW := \033[33m
BLUE := \033[34m
RESET := \033[0m

help: ## Show this help message
	@echo "$(BOLD)$(BLUE)DICTATOR - Makefile Commands$(RESET)"
	@echo "=============================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo ""

sync: ## Install/sync all dependencies with uv
	@echo "$(BOLD)$(BLUE)Syncing dependencies...$(RESET)"
	$(UV) sync
	@echo "$(GREEN)✓ Dependencies synced$(RESET)"

install-dev: sync ## Install in development mode with all dev dependencies
	@echo "$(BOLD)$(BLUE)Installing in development mode...$(RESET)"
	$(UV) pip install -e ".[whisper,translate,audio,test]" --dev
	@echo "$(GREEN)✓ Development installation complete$(RESET)"

install: sync ## Install the package in editable mode (user install)
	@echo "$(BOLD)$(BLUE)Installing package in editable mode...$(RESET)"
	$(UV) pip install -e .
	@echo "$(GREEN)✓ Package installed$(RESET)"
	@echo "$(YELLOW)Run 'dictator' to start the application$(RESET)"

install-system: build ## Install to system with dedicated venv (requires root)
	@echo "$(BOLD)$(BLUE)Installing to system...$(RESET)"
	@echo "$(BLUE)Creating system virtual environment...$(RESET)"
	sudo mkdir -p /opt/dictator
	sudo $(UV) venv /opt/dictator/venv
	@echo "$(BLUE)Installing PyTorch with CUDA 12 support...$(RESET)"
	sudo $(UV) pip install --python /opt/dictator/venv/bin/python torch --index-url https://download.pytorch.org/whl/cu121
	@echo "$(BLUE)Installing dictator package...$(RESET)"
	sudo $(UV) pip install --python /opt/dictator/venv/bin/python dist/*.whl --force-reinstall
	@echo "$(BLUE)Creating system launcher script...$(RESET)"
	@echo '#!/bin/bash' | sudo tee /usr/local/bin/dictator > /dev/null
	@echo 'exec /opt/dictator/venv/bin/python -m src "$$@"' | sudo tee -a /usr/local/bin/dictator > /dev/null
	sudo chmod +x /usr/local/bin/dictator
	@echo "$(GREEN)✓ System installation complete$(RESET)"
	@$(MAKE) update-desktop
	@echo ""
	@echo "$(YELLOW)⚠  Don't forget to run 'make permissions' to set up hotkey support$(RESET)"

uninstall: ## Uninstall the package from current environment
	@echo "$(BOLD)$(BLUE)Uninstalling package...$(RESET)"
	$(UV) pip uninstall $(PROJECT_NAME) -y || true
	@echo "$(GREEN)✓ Package uninstalled$(RESET)"

uninstall-system: ## Uninstall from system (requires root)
	@echo "$(BOLD)$(BLUE)Uninstalling from system...$(RESET)"
	sudo rm -rf /opt/dictator
	sudo rm -f /usr/local/bin/dictator
	sudo rm -f /usr/local/share/applications/dictator.desktop
	sudo rm -f /usr/local/share/pixmaps/dictator.png
	sudo rm -f /usr/local/share/pixmaps/dictator.ico
	@echo "$(GREEN)✓ System uninstallation complete$(RESET)"

run: ## Run the application
	@echo "$(BOLD)$(BLUE)Starting DICTATOR...$(RESET)"
	@export LD_LIBRARY_PATH="/usr/local/cuda-13.1/targets/x86_64-linux/lib:/usr/local/lib64/python3.12/site-packages/ctranslate2.libs:$$LD_LIBRARY_PATH"; \
	$(UV) run python -m $(SRC_DIR)

run-no-tray: ## Run the application without system tray
	@echo "$(BOLD)$(BLUE)Starting DICTATOR (no tray)...$(RESET)"
	@export LD_LIBRARY_PATH="/usr/local/cuda-13.1/targets/x86_64-linux/lib:/usr/local/lib64/python3.12/site-packages/ctranslate2.libs:$$LD_LIBRARY_PATH"; \
	$(UV) run python -m $(SRC_DIR) --no-tray

list-devices: ## List available audio input devices
	@$(UV) run python -m $(SRC_DIR) --list-devices

device-info: ## Show current audio device configuration
	@$(UV) run python -m $(SRC_DIR) --device-info

version: ## Show version information
	@$(UV) run python -m $(SRC_DIR) --version

build: clean sync ## Build distribution packages (wheel)
	@echo "$(BOLD)$(BLUE)Building distribution packages...$(RESET)"
	$(UV) build
	@echo "$(GREEN)✓ Build complete - check dist/ directory$(RESET)"

test: sync ## Run tests
	@echo "$(BOLD)$(BLUE)Running tests...$(RESET)"
	$(UV) run pytest tests/ -v
	@echo "$(GREEN)✓ Tests complete$(RESET)"

test-cov: sync ## Run tests with coverage
	@echo "$(BOLD)$(BLUE)Running tests with coverage...$(RESET)"
	$(UV) run pytest tests/ -v --cov=$(SRC_DIR) --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Tests complete - coverage report in htmlcov/$(RESET)"

clean: ## Clean build artifacts and cache
	@echo "$(BOLD)$(BLUE)Cleaning build artifacts...$(RESET)"
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf src/*.egg-info
	rm -rf .pytest_cache
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "$(GREEN)✓ Cleaned$(RESET)"

permissions: ## Set up permissions for global hotkeys (requires sudo)
	@echo "$(BOLD)$(BLUE)Setting up permissions...$(RESET)"
	@bash $(SCRIPTS_DIR)/setup-permissions.sh

update-desktop: ## Update desktop icon cache (requires root)
	@echo "$(BOLD)$(BLUE)Updating desktop database...$(RESET)"
	@if command -v update-desktop-database >/dev/null 2>&1; then \
		sudo update-desktop-database /usr/local/share/applications/ 2>/dev/null || true; \
	fi
	@if command -v gtk-update-icon-cache >/dev/null 2>&1; then \
		sudo gtk-update-icon-cache /usr/local/share/icons/hicolor/ 2>/dev/null || true; \
	fi
	@echo "$(GREEN)✓ Desktop database updated$(RESET)"

lint: ## Run code linters
	@echo "$(BOLD)$(BLUE)Running linters...$(RESET)"
	$(UV) run black --check $(SRC_DIR)
	$(UV) run isort --check $(SRC_DIR)
	@echo "$(GREEN)✓ Linting complete$(RESET)"

format: ## Format code with black and isort
	@echo "$(BOLD)$(BLUE)Formatting code...$(RESET)"
	$(UV) run black $(SRC_DIR)
	$(UV) run isort $(SRC_DIR)
	@echo "$(GREEN)✓ Code formatted$(RESET)"

dev-setup: sync install-dev permissions ## Complete development setup
	@echo ""
	@echo "$(BOLD)$(GREEN)✓ Development environment ready!$(RESET)"
	@echo ""
	@echo "Quick start:"
	@echo "  make run          - Run the application"
	@echo "  make test         - Run tests"
	@echo "  make help         - Show all commands"
	@echo ""

# Default target
.DEFAULT_GOAL := help
