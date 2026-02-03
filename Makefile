.PHONY: help install lint format type-check security-check test clean build run-falkor run-neptune

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies and setup pre-commit hooks
	uv sync
	uv run pre-commit install

lint: ## Run linting with ruff
	uv run ruff check src/

format: ## Format code with ruff
	uv run ruff format src/

type-check: ## Run type checking with mypy
	uv run mypy src/ws_memory_mcp --ignore-missing-imports

security-check: ## Run security checks with bandit
	uv run bandit -r src/

test: ## Run all tests (placeholder - add when tests are implemented)
	@echo "No tests implemented yet"

check-all: lint type-check security-check ## Run all code quality checks

clean: ## Clean up build artifacts and caches
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build: ## Build the package
	uv build

run-falkor: ## Run server with FalkorDB backend (requires FalkorDB running)
	uv run ws-memory-mcp-server --backend falkordb --falkor-host localhost --falkor-port 6379 --log-level INFO

run-neptune: ## Run server with Neptune backend (requires endpoint)
	@echo "Usage: make run-neptune ENDPOINT=your-neptune-endpoint"
	@if [ -z "$(ENDPOINT)" ]; then echo "Error: ENDPOINT variable is required"; exit 1; fi
	uv run ws-memory-mcp-server --backend neptune --endpoint "$(ENDPOINT)" --log-level INFO

docker-build: ## Build Docker image
	docker build -t ws-memory-mcp-server .

docker-run: ## Run with Docker Compose
	docker-compose up -d

docker-stop: ## Stop Docker Compose
	docker-compose down

docker-logs: ## View Docker logs
	docker-compose logs -f